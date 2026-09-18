"""Account status and local recovery. Diagnostic records contain only fixed messages."""
import ui_language
import copy, datetime as dt, hashlib, json, re, socket, threading, time, uuid
from pathlib import Path

LABELS = {'queued':ui_language.t('Venter'), 'retry':ui_language.t('Venter på nytt forsøk'), 'reserved':ui_language.t('Venter på sending'),
          'sent':ui_language.t('Sendt til LoTW – behandling må kontrolleres'), 'manual-batch':ui_language.t('Krever historisk import hos Club Log'),
          'starting':ui_language.t('Sendt – resultat må kontrolleres'), 'sending':ui_language.t('Sender – venter på kvittering'),
          'ack':ui_language.t('Leveringsresultat venter på Cloud'),
          'delivered':ui_language.t('Bekreftet lagret'), 'uncertain':ui_language.t('Ukjent resultat – kontroller mottaker'),
          'rejected':ui_language.t('Avvist – kontroller innstillinger'), 'changed':ui_language.t('Endret etter levering')}

class History:
    def __init__(self, folder):
        self.path=Path(folder)/'error-history.json';self.lock=threading.RLock()
    def read(self):
        try:return json.loads(self.path.read_text(encoding='utf-8'))[-200:]
        except (OSError,ValueError):return []
    def record(self, area, error):
        from cloud_sync import atomic
        text=str(error).lower()
        if any(x in text for x in ('sertifikat','certificate','ssl','https')):code='tls';message=ui_language.t('Sikker forbindelse kunne ikke bekreftes.')
        elif any(x in text for x in ('passord','logg inn','innlogging','password','sign in','log in','login','401','403')):code='konto';message=ui_language.t('Innlogging eller tilgang må kontrolleres.')
        elif any(x in text for x in ('nett','network','server','tilkob','connection','timeout','timed out')):code='nett';message=ui_language.t('Serverforbindelsen feilet. Kontroller nett og serverstatus.')
        elif isinstance(error,OSError):code='fil';message=ui_language.t('En lokal fil kunne ikke leses eller lagres. Kontroller lagringsplass og filtilgang.')
        elif any(x in text for x in ('konflikt','duplikat','endret','conflict','duplicate','changed')):code='konflikt';message=ui_language.t('Ulike opplysninger trenger kontroll før de kan behandles.')
        else:code='operasjon';message=ui_language.t('Handlingen ble ikke fullført. Kontroller statusvisningen og prøv igjen.')
        area=ui_language.canonical(area);message=ui_language.canonical(message)
        area=area if area in ('Cloud','App','Radio','Gjenoppretting','Loggtjenester') else 'App'
        with self.lock:
            items=self.read();now=time.time()
            if items and items[-1]['area']==area and items[-1]['code']==code and now-items[-1]['last']<300:
                items[-1].update(last=now,count=items[-1]['count']+1)
            else:items.append({'time':now,'last':now,'area':area,'code':code,'message':message,'count':1})
            atomic(self.path,items[-200:])

class Operations:
    def __init__(self,sync):
        self.sync=sync;self.history=History(sync.folder.parent)
        path=sync.folder/'device.json'
        from cloud_sync import atomic
        if not path.exists():atomic(path,{'id':str(uuid.uuid4())})
        self.device=json.loads(path.read_text(encoding='utf-8'))['id']
    def namespace(self):
        c=self.sync.config
        if not c.get('user'):raise ValueError(ui_language.t('Logg inn først.'))
        return hashlib.sha256((c['url']+'|'+c['user']).encode()).hexdigest()
    def local(self):
        from qso_sync import canonical
        return {k:canonical(v) for k,v in self.sync.snapshot().items() if k.startswith('qso/') and v is not None}
    def baseline(self):
        path=self.sync.folder/(self.namespace()+'.json')
        return self.sync.read_private(path) if path.exists() else {}
    def client(self):
        stamp=self.sync.config.get('last_sync_epoch',0)
        baseline=self.baseline() if self.sync.config.get('user') else {}
        pending=sum(baseline.get(k,{}).get('value')!=v for k,v in self.local().items())
        return {'device':self.device,'name':socket.gethostname()[:64],'last_sync':stamp,'pending':pending}
    def overview(self):
        s=self.sync
        with s.lock:
            local=self.local();baseline=self.baseline();contacts=[]
            for key,q in local.items():
                synced=baseline.get(key,{}).get('value')==q
                contacts.append({'key':key,'call':q.get('CALL',''),'date':q.get('QSO_DATE',''),'time':q.get('TIME_ON',''),
                                 'cloud':ui_language.t('I Cloud') if synced else ui_language.t('Venter på Cloud')})
            pending=sum(q['cloud']!=ui_language.t('I Cloud') for q in contacts);s.status['pending_contacts']=pending
            try:devices=s.request('/v1/account/devices',{});device_error=''
            except Exception as e:
                devices={'items':[]};device_error=ui_language.t('Enhetsoversikten kunne ikke hentes. Krever Cloud-server 0.6.2 eller nyere.')
            try:s.deliveries();delivery_error=''
            except Exception:delivery_error=ui_language.t('Leveringsstatus kunne ikke oppdateres. Sist hentede status vises.')
            deliveries=[{k:item.get(k) for k in ('qso','call','date','time','service','profile','state','updated','message')} for item in s.status.get('deliveries',[])]
            from log_delivery import Outbox
            by_id={(d['qso'],d['service'],d['profile']):d for d in deliveries}
            for d in deliveries:
                d['can_resolve']=d['state'] in ('uncertain','rejected')
                d['expected']=d['updated']
            for d in Outbox(s).rows():
                ident=(d['qso'],d['service'],d['profile'])
                remote=by_id.get(ident,{})
                if remote.get('state') not in ('delivered','sent'):
                    d.update(can_resolve=bool(remote.get('can_resolve')),expected=remote.get('expected'))
                    by_id[ident]=d
            deliveries=list(by_id.values())
            for item in deliveries:
                item['label']=ui_language.t(LABELS.get(item['state'],'Ingen bekreftelse'))
                if isinstance(item.get('message'),str):item['message']=ui_language.t(item['message'])
            return {'contacts':sorted(contacts,key=lambda x:(x['date'],x['time']),reverse=True),'total':len(local),'pending':pending,
                    'last_sync':s.config.get('last_sync_epoch',0),'devices':devices,'device_error':device_error,
                    'deliveries':deliveries,'delivery_error':delivery_error,'conflicts':len(s.view().get('conflicts',[])),
                    'errors':[{**item,'area':ui_language.t(item['area']),'message':ui_language.t(item['message'])} for item in self.history.read()]}
    def backup_items(self):
        folder=self.sync.folder/'backups'/self.namespace();items=[]
        for p in sorted(folder.glob('*.json'),reverse=True):
            try:
                data=self.sync.read_private(p);count=sum(k.startswith('qso/') and v is not None for k,v in data['data'].items())
                items.append({'id':p.name,'time':p.stat().st_mtime,'contacts':count})
            except Exception:items.append({'id':p.name,'time':p.stat().st_mtime,'contacts':None,'error':ui_language.t('Sikkerhetskopien kunne ikke leses.')})
        return {'items':items}
    def backup_data(self,name):
        if not isinstance(name,str) or not re.fullmatch(r'[0-9TZ.]+\.json',name):raise ValueError(ui_language.t('Ugyldig sikkerhetskopi.'))
        folder=(self.sync.folder/'backups'/self.namespace()).resolve();path=(folder/name).resolve()
        if path.parent!=folder or not path.is_file():raise ValueError(ui_language.t('Sikkerhetskopien finnes ikke for denne kontoen.'))
        source=self.sync.read_private(path)
        if source.get('format')!=1 or not isinstance(source.get('data'),dict):raise ValueError(ui_language.t('Sikkerhetskopien er ugyldig.'))
        data={k:v for k,v in source['data'].items() if k.startswith('qso/') and v is not None}
        from shared_log import identity
        # Identity and field validation are also performed by the application's apply callback.
        for key,q in data.items():
            if not re.fullmatch('qso/[0-9a-f]{64}',key) or not isinstance(q,dict):raise ValueError(ui_language.t('Ugyldig kontakt i sikkerhetskopien.'))
            if key!='qso/'+hashlib.sha256(json.dumps(identity(q)).encode()).hexdigest():raise ValueError(ui_language.t('Kontaktens identitet stemmer ikke i sikkerhetskopien.'))
            try:dt.datetime.strptime(q['QSO_DATE']+q['TIME_ON'],'%Y%m%d%H%M%S')
            except (ValueError,KeyError):raise ValueError(ui_language.t('Ugyldig dato eller tid i sikkerhetskopien.')) from None
        return data,path.stat().st_mtime
    def preview(self,name):
        with self.sync.lock:
            data,when=self.backup_data(name);local=self.local()
            return {'id':name,'time':when,'contacts':len(data),'current':len(local),'add':len(set(data)-set(local)),
                    'different':sum(k in local and local[k]!=v for k,v in data.items()),'preserved':len(local)}
    def restore(self,name):
        from cloud_sync import atomic
        with self.sync.lock:
            data,_=self.backup_data(name);captured=self.sync.snapshot();incoming={k:v for k,v in data.items() if captured.get(k) is None}
            stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            self.sync.save_private(self.sync.folder/'backups'/self.namespace()/(stamp+'.json'),{'format':1,'data':captured})
            applied=self.sync.apply(incoming,captured)
            return {'added':len(applied),'preserved':sum(k.startswith('qso/') and v is not None for k,v in captured.items()),
                    'skipped':len(incoming)-len(applied),'message':ui_language.t('Manglende kontakter er hentet. Nåværende kontakter og innstillinger er beholdt.')}
    def diagnostics(self):
        s=self.sync
        return {'product':'HamNavigator MY SHACK','version':(Path(__file__).parent/'VERSION').read_text().strip(),
                'platform':'Windows','connected':bool(s.config.get('token')),'authorized':s.authorized,
                'last_sync':s.config.get('last_sync_epoch',0),'errors':self.history.read()}
