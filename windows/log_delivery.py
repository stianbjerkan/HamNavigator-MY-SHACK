"""Durable, encrypted PC outbox. Cloud leases coordinate PC and mobile uploads."""
import ui_language
import copy, hashlib, json, os, re, subprocess, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from shared_log import parse, normalize, identity, locked

SERVICES={'qrz','clublog','eqsl','cloudlog','wavelog','hrdlog','hamcq','lotw'}
HOSTS={'qrz':{'logbook.qrz.com'},'clublog':{'clublog.org'},'eqsl':{'www.eqsl.cc'},'hrdlog':{'www.hrdlog.net'},'hamcq':{'hamcq.cn','www.hamcq.cn','api.hamcq.cn'}}

def result(service,code,body):
    if code==429:return 'retry'
    if code in (401,403):return 'rejected'
    if not 200<=code<300:return 'uncertain'
    if service=='qrz':
        values=dict(urllib.parse.parse_qsl(body))
        if values.get('RESULT')=='OK':return 'delivered'
        if values.get('RESULT') in ('FAIL','AUTH'):return 'rejected'
    if service=='clublog' and re.match(r'^QSO (OK|Duplicate|Modified)\b',body.strip()):return 'delivered'
    if service in ('cloudlog','wavelog'):
        try:
            value=json.loads(body)
            if value.get('status')=='created' and value.get('adif_errors',0)==0 and value.get('adif_count',1)==1:return 'delivered'
            if value.get('status')=='failed':return 'rejected'
        except ValueError:pass
    if service=='eqsl':
        if 'Result: 1 out of 1 records added' in body:return 'delivered'
        if 'Error: No match on eQSL_User/eQSL_Pswd' in body or 'specify the desired User by using the QTHNickname' in body:return 'rejected'
    # HRDLOG/HamCQ replies are retained as unknown until a documented positive
    # receipt is recognized; an HTTP 200 alone is never proof of log storage.
    return 'uncertain'

class Outbox:
    def __init__(self,sync):self.s=sync
    def folder(self):
        c=self.s.config
        if not c.get('token') or not c.get('user'):raise ValueError(ui_language.t('Logg inn i HamNavigator før levering til loggtjenester.'))
        name=hashlib.sha256((c['url']+'|'+c['user']).encode()).hexdigest()
        path=self.s.folder/'outbox'/name;path.mkdir(parents=True,exist_ok=True);return path
    def load(self,p):return self.s.read_private(p)
    def save(self,p,v):self.s.save_private(p,v)
    def enqueue(self,data):
        if not isinstance(data,dict) or len(json.dumps(data))>1000000:raise ValueError(ui_language.t('Ugyldig leveringsforespørsel.'))
        service=data.get('service');profile=str(data.get('profile','')).strip().upper();request=data.get('request',{})
        if service not in SERVICES or not re.fullmatch(r'[A-Za-z0-9_.@/:-]{1,100}',profile):raise ValueError(ui_language.t('Ugyldig loggtjeneste eller kontoprofil.'))
        rows=parse(str(data.get('adif','')))
        if len(rows)!=1:raise ValueError(ui_language.t('Leveringskøen krever én kontakt per forespørsel.'))
        q=normalize(rows[0]);key='qso/'+hashlib.sha256(json.dumps(identity(q)).encode()).hexdigest()
        if not q.get('CALL') or not re.fullmatch(r'\d{8}',q.get('QSO_DATE','')) or not re.fullmatch(r'\d{6}',q.get('TIME_ON','')):raise ValueError(ui_language.t('Kontakten mangler kallesignal eller UTC-dato/tid.'))
        if service=='lotw':
            binary=Path(str(request.get('binary','')))
            if request.get('kind')!='tqsl' or not binary.is_absolute() or binary.name.lower()!='tqsl.exe' or not binary.is_file() or not str(request.get('station','')).strip():raise ValueError(ui_language.t('Velg gyldig TQSL-program og stasjonsprofil.'))
        else:
            url=urllib.parse.urlsplit(str(request.get('url','')))
            if request.get('kind')!='http' or url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment:raise ValueError(ui_language.t('Loggtjenesten krever en gyldig HTTPS-adresse.'))
            if service in HOSTS and url.hostname.lower() not in HOSTS[service]:raise ValueError(ui_language.t('Adressen tilhører ikke den valgte loggtjenesten.'))
            if request.get('method','POST') not in ('GET','POST'):raise ValueError(ui_language.t('Ugyldig forespørsel.'))
        folder=self.folder();job_id=hashlib.sha256((key+'|'+service+'|'+profile).encode()).hexdigest();path=folder/(job_id+'.json')
        with locked(path.with_suffix('.lock')):
            old=self.load(path) if path.exists() else None
            if old and old['state'] not in ('queued','retry','rejected'):return {'id':job_id,'state':old['state']}
            value={'id':job_id,'qso':key,'call':q['CALL'],'date':q['QSO_DATE'],'time':q['TIME_ON'],'service':service,'profile':profile,
                   'request':request,'adif':data['adif'],'created':old['created'] if old else time.time(),'state':old['state'] if old else 'queued','updated':time.time()}
            if old:
                for name in ('ticket','not_before'):
                    if name in old:value[name]=old[name]
            self.save(path,value)
        return {'id':job_id,'state':value['state']}
    def rows(self):
        rows=[]
        for path in self.folder().glob('*.json'):
            try:job=self.load(path)
            except Exception:
                self.s.ops.history.record(ui_language.t('Loggtjenester'),OSError(ui_language.t('Lokal leveringsfil kunne ikke leses.')))
                continue
            rows.append({k:job.get(k) for k in ('id','qso','call','date','time','service','profile','state','updated','message')})
        return rows
    @staticmethod
    def prepare(job,q):
        """Serialize exactly the synchronized contact, retaining provider header fields."""
        from shared_log import dump
        old=job['adif'];parts=re.split(r'<EOH>',old,flags=re.I,maxsplit=1)
        adif=(parts[0]+'<EOH>' if len(parts)==2 else '')+dump([q]).split('<EOH>',1)[1]
        job['adif']=adif;r=job['request']
        if r['kind']=='tqsl':return
        if r.get('method')=='GET':
            url=urllib.parse.urlsplit(r['url']);values=urllib.parse.parse_qsl(url.query,keep_blank_values=True)
            r['url']=urllib.parse.urlunsplit(url._replace(query=urllib.parse.urlencode([(k,adif if k=='ADIFData' else v) for k,v in values])))
        elif r.get('type')=='application/json':
            values=json.loads(r['body'])
            for k in ('ADIF','adif','ADIFData','string'):
                if k in values:values[k]=adif
            r['body']=json.dumps(values)
        else:
            values=urllib.parse.parse_qsl(r['body'],keep_blank_values=True)
            r['body']=urllib.parse.urlencode([(k,adif if k in ('ADIF','adif','ADIFData','string') else v) for k,v in values])
    def tick(self):
        """At most one external send per pass. Persist before each irreversible step."""
        with self.s.lock:
            if not self.s.authorized or not self.s.config.get('token'):return
            folder=self.folder();baseline=self.s.ops.baseline();local=self.s.ops.local()
            for path in sorted(folder.glob('*.json')):
                with locked(path.with_suffix('.lock')):
                    try:j=self.load(path)
                    except Exception:
                        self.s.ops.history.record(ui_language.t('Loggtjenester'),OSError(ui_language.t('Lokal leveringsfil kunne ikke leses.')))
                        continue
                    state=j['state'];args={k:j[k] for k in ('qso','service','profile')}
                    if j.get('ticket'):args['ticket']=j['ticket']
                    if state in ('delivered','sent','cancelled','manual-batch'):continue
                    if state in ('starting','sending'):
                        j.update(state='uncertain',updated=time.time());self.save(path,j);continue
                    if state=='ack':
                        self.s.request('/v1/delivery/complete',{**args,'state':j['result']});j.update(state=j.get('display_result',j['result']),updated=time.time());self.save(path,j);continue
                    q=local.get(j['qso'])
                    if not q or baseline.get(j['qso'],{}).get('value')!=q:continue
                    from qso_sync import canonical
                    payload=hashlib.sha256(json.dumps(canonical(q),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                    self.prepare(j,canonical(q))
                    legacy=False
                    try:remote=self.s.request('/v1/delivery/queue',{**args,'payload':payload})
                    except ValueError as error:
                        if getattr(error,'status',None)!=404:raise
                        legacy=True;remote={'state':state}
                    if remote['state'] in ('delivered','sent'):
                        j.update(state=remote['state'],updated=time.time());self.save(path,j);continue
                    if state in ('uncertain','rejected'):
                        if remote['state']!='retry':continue
                        j.update(state='retry',not_before=0);state='retry';self.save(path,j)
                    if j.get('not_before',0)>time.time():continue
                    if j['service']=='clublog' and time.time()-j['created']>120:
                        j.update(state='manual-batch',message=ui_language.t('Bruk Club Logs historiske import for denne kontakten.'),updated=time.time());self.save(path,j);continue
                    claim=self.s.request('/v1/delivery/claim',{**args,'payload':payload})
                    if not claim.get('allowed'):
                        j.update(state='queued' if claim['state'] in ('reserved','sending') else claim['state'],updated=time.time());self.save(path,j);continue
                    j.update(ticket=claim['ticket'],state='starting',updated=time.time());self.save(path,j);args['ticket']=j['ticket']
                    self.s.request('/v1/delivery/begin',args);j['state']='sending';self.save(path,j)
                    try:outcome=self.send(j)
                    except Exception:outcome='uncertain'
                    cloud_result='uncertain' if legacy and outcome=='sent' else outcome
                    j.update(state='ack',result=cloud_result,display_result=outcome,updated=time.time());
                    if outcome=='retry':j['not_before']=time.time()+300
                    self.save(path,j)
                    if outcome in ('rejected','uncertain'):self.s.ops.history.record(ui_language.t('Loggtjenester'),ValueError(ui_language.t('Leveringsresultatet må kontrolleres hos mottaker.')))
                    self.s.request('/v1/delivery/complete',{**args,'state':cloud_result});j['state']=outcome;self.save(path,j);return
    def send(self,job):
        request=job['request']
        if request['kind']=='tqsl':
            import tempfile
            with tempfile.TemporaryDirectory(prefix='hamnavigator-lotw-') as temp:
                file=Path(temp)/'kontakt.adi';file.write_text('HamNavigator\n<EOH>\n'+job['adif'],encoding='utf-8')
                args=[request['binary'],'-a','all','-l',request['station'],'-q','-x','-d','-u',str(file)]
                if request.get('password'):args+=['-p',request['password']]
                try:r=subprocess.run(args,capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                except subprocess.TimeoutExpired:return 'uncertain'
                return 'sent' if b'Final Status: Success' in r.stderr else 'uncertain'
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        req=urllib.request.Request(request['url'],None if request.get('method')=='GET' else str(request.get('body','')).encode(),
                                   {'Content-Type':request.get('type','application/x-www-form-urlencoded'),'User-Agent':'HamNavigator'},method=request.get('method','POST'))
        try:
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as response:
                body=response.read(1000001)
                if len(body)>1000000:return 'uncertain'
                return result(job['service'],response.status,body.decode('utf-8',errors='replace'))
        except urllib.error.HTTPError as error:return result(job['service'],error.code,'')

def enqueue_from_map(data):
    """Called by the bundled Python bridge; inherits the real HamNavigator data path."""
    from types import SimpleNamespace
    from cloud_sync import Sync
    root=Path(os.environ.get('RADIOASSISTENT_DATA',str(Path(os.environ['APPDATA'])/'Radioassistent')))
    folder=root/'cloud';config=json.loads((folder/'connection.json').read_text(encoding='utf-8'))
    ctx=SimpleNamespace(folder=folder,config=config)
    ctx.read_private=lambda p:Sync.read_private(ctx,p);ctx.save_private=lambda p,v:Sync.save_private(ctx,p,v)
    return Outbox(ctx).enqueue(data)

if __name__=='__main__':
    import sys
    try:
        raw=sys.stdin.buffer.read(1000001)
        if len(raw)>1000000:raise ValueError(ui_language.t('For stor forespørsel.'))
        print(json.dumps(enqueue_from_map(json.loads(raw))))
    except Exception:
        print(json.dumps({'error':ui_language.t('Leveringen kunne ikke legges i kø. Kontakten er fortsatt i lokal logg. Åpne Status og sikkerhetskopi i HamNavigator.')}));sys.exit(1)
