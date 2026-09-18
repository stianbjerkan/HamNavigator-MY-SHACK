"""First-run setup for the redistributable bundle; inactive in the developer app."""
import ui_language
from pathlib import Path
import json
import os
import shutil
import tempfile

def bundled(root):
    return (Path(root)/'BUNDLE.json').is_file()

def program_defaults(root, data_dir):
    root, data_dir = Path(root), Path(data_dir)
    if not bundled(root):
        return {}
    if (root/'release/HamNavigator/HamNavigator.exe').is_file():
        return {}
    return {'mshv_path':str(data_dir/'programs/MSHV/MSHV_WIN64.exe'),
            'gridtracker_path':str(root/'programs/GridTracker/GridTracker2.exe')}

def prepare_bundle(root, data_dir):
    root, data_dir = Path(root), Path(data_dir)
    import settings_transfer
    try:
        settings_transfer.apply_pending(root,data_dir)
        (data_dir/'cloud/settings-error.txt').unlink(missing_ok=True)
    except Exception as error:
        (data_dir/'cloud').mkdir(parents=True,exist_ok=True)
        (data_dir/'cloud/settings-error.txt').write_text(str(error),encoding='utf-8')
    if not bundled(root):
        return
    if (root/'release/HamNavigator/HamNavigator.exe').is_file():
        # Clean archives can omit the empty directory required by the native logger.
        (root/'release/HamNavigator/log').mkdir(parents=True, exist_ok=True)
        profile=data_dir.parent/'HamNavigator-Map'/'Ginternal'
        profile.mkdir(parents=True,exist_ok=True)
        settings_file=profile/'app-settings.json'
        shared_path=str(data_dir/'log/hamnavigator.adi')
        if settings_file.exists():
            settings=json.loads(settings_file.read_text(encoding='utf-8-sig'))
            logs=settings.get('appLogs',[])
            cleaned=[entry for entry in logs if Path(entry.get('file','')).name.lower() not in ('hamnavigatorlog.adi','hamnavigator.adi')]
            updated=[{'enabled':True,'file':shared_path}]+cleaned
            if logs!=updated:
                backup=settings_file.with_name('before-shared-log-settings.json')
                if not backup.exists():shutil.copy2(settings_file,backup)
                settings['appLogs']=updated
                temp=settings_file.with_suffix('.shared.tmp');temp.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,settings_file)
        return  # HamNavigator keeps its own settings; Map seeds its own profile.
    target=data_dir/'programs/MSHV'
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='mshv-new-',dir=target.parent))
        try:
            shutil.copytree(root/'programs/MSHV',staging,dirs_exist_ok=True)
            try: os.rename(staging,target)
            except FileExistsError: pass
        finally:
            if staging.exists():
                if not staging.resolve().is_relative_to(target.parent.resolve()):
                    raise RuntimeError(ui_language.t('Uventet midlertidig mappe.'))
                shutil.rmtree(staging)
    profile=data_dir/'GridTracker/Ginternal'
    profile.mkdir(parents=True,exist_ok=True)
    path=profile/'app-settings.json'
    if not path.exists():
        # GridTracker deep-merges this clean seed with its factory defaults.
        settings={'defaultsApplied':True,'app':{'multicast':False,'wsjtUdpPort':2237,
            'wsjtForwardUdpEnable':True,'wsjtForwardUdpIp':'127.0.0.1','wsjtForwardUdpPort':2238}}
        try:
            with path.open('x',encoding='utf-8') as f: json.dump(settings,f,indent=2)
        except FileExistsError: pass

def launch_arguments(key, root, data_dir):
    if key=='gridtracker' and bundled(root):
        return ['--user-data-dir='+str(Path(data_dir)/'GridTracker'), '--disable-auto-updates']
    return []
