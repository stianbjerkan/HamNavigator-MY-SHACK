"""Capture settings and stage incoming changes until the next application start."""
import ui_language
import base64,copy,datetime,json,os
from pathlib import Path

FILES={'map/preferences':('app-settings.json','windows.json'), 'digital/preferences':('ms_macros','ms_mesages','ms_settings','ms_start','ms_stinfonet')}
PUBLIC=('call','grid','watch','radio_notes','modules')
LOCAL_PATHS=('mshv_path','gridtracker_path')
def folder(key,root,data):
    return Path(data).parent/'HamNavigator-Map/Ginternal' if key=='map/preferences' else Path(root)/'release/HamNavigator/settings'
def read_private(path):
    from cloud_sync import protect
    return json.loads(protect(json.loads(path.read_text(encoding='utf-8'))['protected'],True))
def save_private(path,value):
    from cloud_sync import protect,atomic
    atomic(path,{'protected':protect(json.dumps(value,ensure_ascii=False))})
def raw_snapshot(root,data,settings):
    result={'setting/preferences':{k:copy.deepcopy(v) for k,v in settings.items() if k not in PUBLIC+LOCAL_PATHS}}
    for key,names in FILES.items():
        files={}
        for name in names:
            path=folder(key,root,data)/name
            if path.is_file():
                raw=path.read_bytes()
                if len(raw)>100000:raise ValueError(ui_language.t('En innstillingsfil er for stor: ')+name)
                if key=='map/preferences' and name=='app-settings.json':
                    config=json.loads(raw.decode('utf-8-sig'))
                    # Absolute paths and active log queues belong to this device.
                    config.pop('appLogs',None);config.pop('trustedQsl',None)
                    raw=json.dumps(config,ensure_ascii=False,separators=(',',':')).encode()
                files[name]=base64.b64encode(raw).decode('ascii')
        if files:result[key]=files
    return result
def snapshot(root,data,settings):
    result=raw_snapshot(root,data,settings);pending=Path(data)/'cloud/settings-pending.json'
    if pending.exists():
        for key,item in read_private(pending).items():
            if item.get('blocked'):continue
            if key=='map/preferences' and isinstance(result.get(key),dict):
                from settings_merge import merge_map
                merged,conflicts=merge_map(result[key],item['value'],item['before'])
                if not conflicts:result[key]=merged
            elif result.get(key)==item['before']:result[key]=item['value']
    return result
def validate(key,value):
    if value is None:raise ValueError(ui_language.t('Innstillinger slettes ikke automatisk fra en annen PC.'))
    if not isinstance(value,dict):raise ValueError(ui_language.t('Ugyldig innstillingsformat.'))
    if key=='setting/preferences':
        if any(k in PUBLIC+LOCAL_PATHS for k in value):raise ValueError(ui_language.t('Ugyldig lokal innstilling.'))
        return
    if key not in FILES or any(n not in FILES[key] for n in value):raise ValueError(ui_language.t('Ukjent innstillingsfil.'))
    for name,encoded in value.items():
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)>100000:raise ValueError(ui_language.t('Innstillingsfilen er for stor.'))
        if name.endswith('.json') and not isinstance(json.loads(raw.decode('utf-8-sig')),dict):raise ValueError(ui_language.t('Ugyldig JSON-innstilling.'))
def stage(key,value,root,data,settings):
    validate(key,value)
    path=Path(data)/'cloud/settings-pending.json';pending=read_private(path) if path.exists() else {}
    current=raw_snapshot(root,data,settings)
    pending[key]={'before':current.get(key),'value':value};save_private(path,pending)
def pending_conflicts(data):
    path=Path(data)/'cloud/settings-pending.json'
    pending=read_private(path) if path.exists() else {}
    return [{'key':key,'local':ui_language.t('Lokale innstillinger er endret etter nedlasting'),
             'cloud':ui_language.t('Beskyttede innstillinger i Cloud'),'fields':item['blocked']}
            for key,item in pending.items() if item.get('blocked')]

def discard_pending(data,keys):
    """Remove only settings whose explicit local choice was accepted by Cloud."""
    if not keys:return
    path=Path(data)/'cloud/settings-pending.json'
    if not path.exists():return
    pending=read_private(path)
    for key in keys:pending.pop(key,None)
    if pending:save_private(path,pending)
    else:path.unlink()

def apply_pending(root,data):
    root,data=Path(root),Path(data);path=data/'cloud/settings-pending.json'
    if not path.exists():return {'applied':[],'blocked':[]}
    data_file=data/'data.json';state=json.loads(data_file.read_text(encoding='utf-8')) if data_file.exists() else {'settings':{}}
    current=raw_snapshot(root,data,state.get('settings',{}));pending=read_private(path);writes={};applied=[];remaining={}
    for key,item in pending.items():
        validate(key,item['value'])
        value=item['value'];conflicts=[]
        if key=='map/preferences' and isinstance(current.get(key),dict):
            from settings_merge import merge_map
            value,conflicts=merge_map(current[key],value,item['before'])
        elif current.get(key)!=item['before'] and current.get(key)!=value:
            conflicts=[ui_language.t('Lokale innstillinger ble endret etter nedlasting')]
        if conflicts:
            # Digital writes settings on exit. Its conflict must not block Map
            # credentials or other independent settings, nor overwrite edits.
            remaining[key]={**item,'blocked':conflicts}
            continue
        applied.append(key)
        if key=='setting/preferences':
            state.setdefault('settings',{}).update(value);writes[data_file]=json.dumps(state,ensure_ascii=False,indent=2).encode()
        else:
            for name,encoded in value.items():
                dest=folder(key,root,data)/name;raw=base64.b64decode(encoded)
                if key=='map/preferences' and name=='app-settings.json':
                    incoming=json.loads(raw.decode('utf-8-sig'));existing=json.loads(dest.read_text(encoding='utf-8-sig')) if dest.exists() else {}
                    for local in ('appLogs','trustedQsl'):
                        if local in existing:incoming[local]=existing[local]
                    # The new PC must locate its own TQSL binary/certificates.
                    raw=json.dumps(incoming,ensure_ascii=False,indent=2).encode()
                writes[dest]=raw
    originals={str(p):base64.b64encode(p.read_bytes()).decode() if p.exists() else None for p in writes}
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    if writes:save_private(data/'cloud/settings-backups'/(stamp+'.json'),originals)
    completed=[]
    try:
        for dest,raw in writes.items():
            dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_suffix(dest.suffix+'.cloud-tmp');temp.write_bytes(raw);os.replace(temp,dest);completed.append(dest)
        # Retain the complete pending payload if applying or committing fails.
        if remaining:save_private(path,remaining)
        else:path.unlink()
    except Exception:
        for dest in writes:
            dest.with_suffix(dest.suffix+'.cloud-tmp').unlink(missing_ok=True)
        for dest in completed:
            raw=originals[str(dest)]
            if raw is None:dest.unlink(missing_ok=True)
            else:dest.write_bytes(base64.b64decode(raw))
        raise
    return {'applied':applied,'blocked':list(remaining)}
