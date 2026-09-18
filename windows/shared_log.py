"""One authoritative ADIF log, with locked atomic writes and three-way edits.

Digital's table and MY SHACK's JSON are projections, never independent logs.
The command line bridge uses the same implementation as the desktop backend.
"""
import ui_language
import copy,datetime,hashlib,json,os,re,sys,time,uuid
from pathlib import Path
from contextlib import contextmanager

ID='APP_HAMNAVIGATOR_ID'
BANDS={'2190M':'.136','630M':'.472','160M':'1.8','80M':'3.5','60M':'5.3','40M':'7','30M':'10.1','20M':'14','17M':'18.068','15M':'21','12M':'24.89','10M':'28','6M':'50','4M':'70','2M':'144','70CM':'432','23CM':'1296'}
MODES={'0':'NON','1':'SSB','2':'CW','6':'FM','10':'JTMS','11':'FSK441','12':'ISCAT-A','13':'ISCAT-B','14':'JT6M','15':'FSK315','17':'MSK144','18':'JT65A','19':'JT65B','20':'JT65C','21':'PI4','22':'FT8','23':'MSKMS','24':'FT4','25':'Q65A','26':'Q65B','27':'Q65C','28':'Q65D','29':'FT2'}

def parse(text):
    result=[];row={};pos=0;tag=re.compile(r'<([A-Za-z0-9_]+)(?::(\d+)(?::[A-Za-z])?)?>')
    while (m:=tag.search(text,pos)):
        key,length=m.group(1).upper(),m.group(2);pos=m.end()
        if length is not None:
            end=pos+int(length)
            if end>len(text):raise ValueError(ui_language.t('Avkortet ADIF-felt: ')+key)
            row[key]=text[pos:end];pos=end
        elif key=='EOH':row={}
        elif key=='EOR':
            if row:result.append(row)
            row={}
    if row:raise ValueError(ui_language.t('ADIF mangler EOR. Originalen er beholdt.'))
    return result

def normalize(row):
    q={str(k).upper():str(v) for k,v in row.items() if k!='id' and v is not None and str(v)!=''}
    for k in ('CALL','BAND','MODE','SUBMODE','STATION_CALLSIGN','GRIDSQUARE','MY_GRIDSQUARE'):
        if k in q:q[k]=q[k].strip().upper()
    for k in ('TIME_ON','TIME_OFF'):
        if len(q.get(k,''))==4:q[k]+='00'
    if q.get('MODE')=='FT4':q.update(MODE='MFSK',SUBMODE='FT4')
    if 'FREQ' in q:
        try:q['FREQ']=format(float(q['FREQ']),'.9g')
        except ValueError:pass
    return q

def identity(q):
    return tuple(q.get(k,'').upper() for k in ('CALL','QSO_DATE','TIME_ON','BAND','MODE','SUBMODE','STATION_CALLSIGN','MY_SIG_INFO','SIG_INFO','MY_SOTA_REF','SOTA_REF'))

def dump(rows):
    out=['HamNavigator shared log\n<ADIF_VER:5>3.1.6<PROGRAMID:12>HamNavigator<EOH>\n']
    for q in rows:
        out.append(''.join(f'<{k}:{len(str(v))}>{v}' for k,v in q.items() if re.fullmatch('[A-Z][A-Z0-9_]*',k) and v!='')+'<EOR>\n')
    return ''.join(out)

def atomic(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8',newline='') as f:f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

@contextmanager
def locked(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a+b') as f:
        f.seek(0,2)
        if f.tell()==0:f.write(b'0');f.flush()
        limit=time.monotonic()+20
        while True:
            try:
                f.seek(0)
                if os.name=='nt':
                    import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl;fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>limit:raise RuntimeError(ui_language.t('Loggboken er opptatt. Prøv igjen.'))
                time.sleep(.05)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

def archive(path):
    if path.exists():
        target=path.parent/'backups'/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8]+'-'+path.name)
        target.parent.mkdir(exist_ok=True);target.write_bytes(path.read_bytes())

def edim_rows(text,station=''):
    rows=[]
    for line in text.splitlines():
        a=line.split(';')
        if len(a)<11 or not re.fullmatch(r'\d{8}',a[0]):continue
        a+=['']*30
        q={'QSO_DATE':a[0],'TIME_ON':a[1]+(a[18] or '00'),'QSO_DATE_OFF':a[2],'TIME_OFF':a[3]+(a[20] or a[18] or '00'),'CALL':a[4],'MODE':MODES.get(a[5],a[5]),'RST_SENT':a[6],'RST_RCVD':a[7],'GRIDSQUARE':a[8],'COMMENT':a[11],'PROP_MODE':a[12],'STX':a[13],'SRX':a[14],'APP_MSHV_EXCHANGE_TX':a[15],'APP_N1MM_EXCHANGE1':a[16],'DISTANCE':a[21],'SAT_NAME':a[22],'SAT_MODE':a[23],'FREQ_RX':a[24],'STATION_CALLSIGN':station}
        try:q['FREQ']=format(float(a[10])/1000,'.9g')
        except ValueError:pass
        for band,f in BANDS.items():
            label=format(float(f),'.9g')+'M'
            if a[9].upper()==label.upper() or (a[9]=='1.8M' and band=='160M'):q['BAND']=band;break
        if not q.get('BAND') and q.get('FREQ'):
            # Native band labels commonly use integer MHz.
            for band,f in reversed(list(BANDS.items())):
                if float(q['FREQ'])>=float(f):q['BAND']=band;break
        q['APP_HAMNAVIGATOR_NATIVE_ORIGINAL']=line
        rows.append(normalize(q))
    return rows

class SharedLog:
    def __init__(self,data_dir,root=None):
        self.data=Path(data_dir);self.root=Path(root) if root else None;self.path=self.data/'log/hamnavigator.adi'
    def _read(self):return parse(self.path.read_text(encoding='utf-8-sig'))
    def _write(self,rows):
        text=dump(rows)
        if self.path.exists() and self.path.read_text(encoding='utf-8-sig')==text:return
        archive(self.path);atomic(self.path,text)
    def initialize(self):
        with locked(self.path):
            if self.path.exists():return self._read()
            sources=[];old=self.data/'data.json';station=''
            if old.exists():
                d=json.loads(old.read_text(encoding='utf-8-sig'));station=d.get('settings',{}).get('call','');sources.append((old,[normalize(q) for q in d.get('qsos',[])]))
            if self.root:
                folder=self.root/'release/HamNavigator/log'
                for name in ('hamnavigatorlog.adi','mshvlog.adi','hamnavigatorlog.edim','mshvlog.edim'):
                    p=folder/name
                    if p.exists():
                        txt=p.read_text(encoding='utf-8-sig');sources.append((p,edim_rows(txt,station) if p.suffix=='.edim' else [normalize(q) for q in parse(txt)]))
            merged=[];conflicts=[]
            migration=self.data/'log/migration-originals';migration.mkdir(parents=True,exist_ok=True)
            for p,rows in sources:
                backup=migration/(hashlib.sha256(str(p).encode()).hexdigest()[:8]+'-'+p.name)
                if not backup.exists():backup.write_bytes(p.read_bytes())
                for q in rows:
                    candidates=[r for r in merged if identity(r)==identity(q)]
                    if not candidates:
                        core=identity(q);candidates=[r for r in merged if all(a==b for i,(a,b) in enumerate(zip(identity(r),core)) if i!=6) and (not r.get('STATION_CALLSIGN') or not q.get('STATION_CALLSIGN'))]
                    if len(candidates)!=1:q[ID]=q.get(ID) or uuid.uuid4().hex;merged.append(q);continue
                    r=candidates[0]
                    for k,v in q.items():
                        if k==ID:continue
                        if not r.get(k):r[k]=v
                        elif r[k]!=v:
                            conflicts.append({'id':r[ID],'field':k,'kept':r[k],'alternate':v,'source':str(p)})
            atomic(migration/'report.json',json.dumps({'source_counts':{str(p):len(q) for p,q in sources},'merged':len(merged),'field_differences':conflicts},ensure_ascii=False,indent=2))
            self._write(merged);return merged
    def read(self):
        if not self.path.exists():self.initialize()
        with locked(self.path):return self._read()
    def commit(self,before,after):
        before={q[ID]:normalize(q) for q in before};after={q[ID]:normalize(q) for q in after}
        with locked(self.path):
            rows=self._read();current={q[ID]:q for q in rows}
            for uid,old in before.items():
                if uid not in after:
                    if uid not in current:continue
                    if current.get(uid)!=old:raise RuntimeError(ui_language.t('Kontakten er endret i et annet vindu. Last loggen på nytt før sletting.'))
                    current.pop(uid,None)
            for uid,new in after.items():
                old=before.get(uid)
                if old is None:
                    matches=[q for q in current.values() if identity(q)==identity(new)]
                    if matches:
                        target=matches[0]
                        for k,v in new.items():
                            if k!=ID and not target.get(k):target[k]=v
                        continue
                    current[uid]=new;continue
                if old==new:continue
                if uid not in current:raise RuntimeError(ui_language.t('Kontakten ble slettet i et annet vindu. Endringen er ikke overskrevet.'))
                target=current[uid]
                for k in old.keys()|new.keys():
                    if k==ID or old.get(k)==new.get(k):continue
                    if target.get(k)!=old.get(k) and target.get(k)!=new.get(k):raise RuntimeError(ui_language.t('Samtidig endring av ')+k+ui_language.t('. Originaldata er beholdt.'))
                    if k in new:target[k]=new[k]
                    else:target.pop(k,None)
            result=list(current.values());self._write(result);return result

def native_view(q):
    t=q.get('TIME_ON','000000').ljust(6,'0');end=q.get('TIME_OFF',t).ljust(6,'0');f=q.get('FREQ',BANDS.get(q.get('BAND'),'0'))
    try:khz=str(round(float(f)*1000))
    except ValueError:khz='0'
    mode=q.get('SUBMODE') or q.get('MODE','NON');band=BANDS.get(q.get('BAND'),'0')
    label=format(float(band),'.9g')+' MHz'
    return [q.get('QSO_DATE',''),t[:2]+':'+t[2:4],q.get('QSO_DATE_OFF',q.get('QSO_DATE','')),end[:2]+':'+end[2:4],q.get('CALL',''),q.get('GRIDSQUARE',''),q.get('RST_SENT',''),q.get('RST_RCVD',''),mode,label,khz,q.get('PROP_MODE',''),q.get('COMMENT',''),t[4:6],q.get('STX',''),q.get('SRX',''),q.get('APP_MSHV_EXCHANGE_TX',''),q.get('APP_N1MM_EXCHANGE1',''),'0','0',end[4:6],q.get('DISTANCE',''),q.get('SAT_NAME',''),q.get('SAT_MODE',''),q.get('FREQ_RX','')]

def bridge(request,store):
    rows=store.initialize()
    if request.get('action')=='commit':
        base=request['canonical'];old={r['id']:normalize(parse(r['adif'])[0]) for r in request['before']};after=[]
        baseby={q[ID]:q for q in base}
        for row in request['after']:
            uid=row['id'];p=normalize(parse(row['adif'])[0]);q=copy.deepcopy(baseby.get(uid,{ID:uid}))
            if uid not in old:
                q.update(p);q[ID]=uid
                state_path=store.data/'data.json'
                if state_path.exists():
                    portable=json.loads(state_path.read_text(encoding='utf-8-sig')).get('portable',{})
                    if portable.get('active'):
                        from portable_ops import activation_fields
                        q=activation_fields(q,portable)
            else:
                for key in old[uid].keys()|p.keys():
                    if old[uid].get(key)!=p.get(key):
                        if key in p:q[key]=p[key]
                        else:q.pop(key,None)
            after.append(q)
        rows=store.commit(base,after)
    result={'rows':rows,'view':[native_view(q) for q in rows],'path':str(store.path),'revision':hashlib.sha256(dump(rows).encode()).hexdigest()}
    if request.get('action')=='commit':result['baseline']=after
    return result

if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.buffer.read().decode('utf-8'));data=os.environ.get('RADIOASSISTENT_DATA') or str(Path(os.environ['APPDATA'])/'Radioassistent')
        result=bridge(request,SharedLog(data,Path(__file__).resolve().parent));sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
    except Exception as exc:
        sys.stdout.buffer.write(json.dumps({'error':str(exc)},ensure_ascii=False).encode('utf-8'));sys.exit(1)
