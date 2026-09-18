"""Versioned contact sync and encrypted account settings; device control stays local."""
import ui_language
import base64, copy, ctypes, datetime, hashlib, json, os, socket, ssl, threading, urllib.request, urllib.error, urllib.parse
from pathlib import Path
import account_vault as vault
import time
from cloud_network import HTTPSHandler
from hmac import compare_digest as secrets_equal
from cloud_transport import exchange,PUBLIC_CLOUD
from qso_sync import canonical, canonical_objects, contact_merge, MISSING

def certificate_path(value):
    value=str(value or '').strip()
    if len(value)>1 and value[0]==value[-1] and value[0] in ('"', "'"):
        value=value[1:-1].strip()
    return value

def server_identity(address):
    """Compare servers without treating URL paths as case-insensitive."""
    try:
        value=urllib.parse.urlsplit(address)
        if value.scheme!='https' or not value.hostname or value.username or value.password or value.query or value.fragment:return None
        return value.hostname.lower(),value.port or 443,value.path.rstrip('/')
    except ValueError:return None

def connection_error(error):
    reason=getattr(error,'reason',error)
    if isinstance(reason,ssl.SSLCertVerificationError):
        return ui_language.t('Sertifikatet til Cloud-serveren kunne ikke bekreftes. Kontroller serveradressen og sertifikatet under «Avansert: egen server».')
    if isinstance(reason,socket.gaierror) or (isinstance(reason,TimeoutError) and 'servernavnet' in str(reason)):
        return ui_language.t('Servernavnet kunne ikke finnes. Kontroller serveradressen under «Avansert: egen server».')
    if isinstance(reason,TimeoutError):
        return ui_language.t('Cloud-serveren svarte ikke i tide. Kontroller nettforbindelsen og prøv igjen.')
    if isinstance(reason,ConnectionRefusedError) or getattr(reason,'winerror',None)==10061:
        return ui_language.t('Cloud-serveren avviste tilkoblingen. Kontroller at serveren kjører og at adressen og porten er riktige.')
    if isinstance(reason,ssl.SSLError):
        return ui_language.t('En sikker forbindelse til Cloud-serveren kunne ikke opprettes. Kontroller serverens HTTPS-oppsett.')
    return ui_language.t('Kunne ikke nå Cloud-serveren. Kontroller nettforbindelsen og serveradressen.')

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)

def protect(text, decrypt=False):
    """Windows current-user DPAPI; tokens are never written as clear text."""
    if os.name!='nt':raise ValueError(ui_language.t('Denne klienten krever Windows DPAPI.'))
    class Blob(ctypes.Structure):_fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=base64.b64decode(text) if decrypt else text.encode()
    buf=ctypes.create_string_buffer(raw);src=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
    fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out)):raise ValueError(ui_language.t('Kunne ikke åpne den lagrede innloggingen. Logg inn på nytt.'))
    try:
        result=ctypes.string_at(out.data,out.size)
        return result.decode() if decrypt else base64.b64encode(result).decode()
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(out.data)

class Sync:
    def __init__(self,folder,snapshot,apply):
        self.folder=Path(folder)/'cloud';self.folder.mkdir(parents=True,exist_ok=True)
        self.snapshot=snapshot;self.apply=apply;self.lock=threading.RLock();self.config={};self.status={'message':ui_language.t('Ikke tilkoblet'),'conflicts':[]};self.stop=threading.Event();self.wake=threading.Event();self.started_at=None;self.last_finished=None;self.worker=None;self.backup_digest=None
        if (self.folder/'connection.json').exists():self.config=json.loads((self.folder/'connection.json').read_text(encoding='utf-8'))
        if not self.config.get('url'):self.config.update(url=PUBLIC_CLOUD,certificate='')
        self.authorized=False;self.is_admin=False;self.last_presence=0;self.cursor_sessions=set()
        from operations import Operations
        self.ops=Operations(self)
    def request(self,path,data,*,config=None,authenticated=True,method='POST'):
        target=self.config if config is None else config
        address=target.get('url','');parsed=urllib.parse.urlsplit(address)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError(ui_language.t('Bruk en HTTPS-adresse til HamNavigator Cloud.'))
        cert=certificate_path(target.get('certificate'))
        try:context=ssl.create_default_context(cafile=cert or None)
        except (OSError,ValueError):raise ValueError(ui_language.t('Sertifikatfilen kan ikke leses. Velg den lagrede .crt-filen på denne PC-en.')) from None
        headers={'Content-Type':'application/json'}
        if authenticated and target.get('token'):headers['Authorization']='Bearer '+protect(target['token'],True)
        req=urllib.request.Request(address.rstrip('/')+path,data=None if method=='GET' else json.dumps(data).encode(),headers=headers,method=method)
        # Redirects are not followed: an access token must stay on the configured server.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        opener=urllib.request.build_opener(HTTPSHandler(context, parsed.hostname, target.get('connect_ip','')),NoRedirect())
        try:
            result=exchange(opener,req,address)
            if isinstance(result,dict) and isinstance(result.get('message'),str):
                result={**result,'message':ui_language.t(result['message'])}
            return result
        except urllib.error.HTTPError as e:
            if e.code==401 and authenticated and config is None and self.config.get('token'):
                self.authorized=False;self.is_admin=False
                self.config.pop('token',None);self.config['automatic']=False;atomic(self.folder/'connection.json',self.config)
                self.status={'message':ui_language.t('Innloggingen er utløpt eller serveren er startet på nytt. Logg inn igjen. Lokale kontakter er beholdt.'),'conflicts':[]}
            try:message=json.loads(e.read(4096)).get('error',ui_language.t('Serveren avviste forespørselen.'))
            except Exception:message=ui_language.t('Serveren avviste forespørselen.')
            error=ValueError(ui_language.t(message));error.status=e.code
            raise error from None
        except (urllib.error.URLError,TimeoutError) as error:raise ValueError(connection_error(error)) from None
    def connection_settings(self,data):
        address=str(data.get('url',self.config.get('url',PUBLIC_CLOUD))).strip().rstrip('/')
        identity=server_identity(address)
        same=identity is not None and identity==server_identity(self.config.get('url',''))
        default_certificate=self.config.get('certificate','') if same else ''
        config={'url':address,'certificate':certificate_path(data.get('certificate',default_certificate))}
        # A saved LAN destination belongs only to this exact server. It must
        # survive login/reset/check forms, but never redirect a different server.
        if same and self.config.get('connect_ip'):config['connect_ip']=self.config['connect_ip']
        return config
    def check_connection(self,data):
        config=self.connection_settings(data)
        result=self.request('/v1/auth/options',{},config=config,authenticated=False,method='GET')
        if result.get('service')!='HamNavigator Cloud' or result.get('registration') not in ('open','invite','closed'):
            raise ValueError(ui_language.t('Adressen er ikke en støttet HamNavigator Cloud-server.'))
        return {**config,**result,'message':ui_language.t('Sikker forbindelse opprettet.')}
    def import_connection(self,data):
        text=data.get('text','')
        if not isinstance(text,str) or len(text)>65536:raise ValueError(ui_language.t('Tilkoblingsfilen er ugyldig.'))
        value=json.loads(text)
        if not isinstance(value,dict) or value.get('format')!='hamnavigator-cloud' or value.get('version')!=1:raise ValueError(ui_language.t('Velg en .hamcloud-fil fra serverprogrammet.'))
        pem=value.get('certificate','')
        if not isinstance(pem,str) or len(pem)>16384 or 'PRIVATE KEY' in pem:raise ValueError(ui_language.t('Tilkoblingsfilen har et ugyldig sertifikat.'))
        try:ssl.create_default_context(cadata=pem)
        except (ssl.SSLError,ValueError):raise ValueError(ui_language.t('Sertifikatet i tilkoblingsfilen er ugyldig.')) from None
        path=self.folder/'certificates'/(hashlib.sha256(pem.encode()).hexdigest()+'.crt');path.parent.mkdir(exist_ok=True)
        if not path.exists():path.write_text(pem,encoding='ascii')
        return self.check_connection({'url':value.get('url',''),'certificate':str(path)})
    def verify(self):
        with self.lock:
            if not self.config.get('token'):return self.view()
            self.presence()
            self.status['message']=ui_language.t('Logget inn som ')+self.config.get('email','')+'.'
            return self.view()
    def presence(self):
        with self.lock:
            self.last_presence=time.monotonic()
            if not self.config.get('token'):
                self.authorized=False;self.is_admin=False;return
            version=(Path(__file__).parent/'VERSION').read_text().strip()
            result=self.request('/v1/account/me',{'client':{'platform':'Windows','version':version,**self.ops.client()}})
            if result.get('user')!=self.config.get('user'):raise ValueError(ui_language.t('Serveren bekreftet ikke kontoen. Logg inn på nytt.'))
            self.authorized=True;self.is_admin=result.get('admin') is True
    def admin_users(self,data):
        # The server independently verifies owner permissions for every request.
        with self.lock:
            self.presence()
            if not self.is_admin:raise ValueError(ui_language.t('Bare administratoren har tilgang til brukeroversikten.'))
            return self.request('/v1/admin/users',{k:data[k] for k in ('offset','search','active_only') if k in data})
    def configure_vault(self,password,recovery,previous):
        user=self.config['user'];remote=self.request('/v1/vault/key',{});key=None
        if remote['value'] is None:
            key=os.urandom(32);remote=self.request('/v1/vault/key',{'revision':0,'value':vault.wrap(key,password,user)})
            if remote.get('conflict'):key=None
        if key is None:
            try:key=vault.unwrap(remote['value'],password,user)
            except (ValueError,KeyError,TypeError):
                if previous.get('user')==user and previous.get('url')==self.config['url'] and previous.get('vault_key'):
                    key=vault.un64(protect(previous['vault_key'],True))
                elif recovery:
                    try:key=vault.recovery_key(recovery)
                    except Exception:raise ValueError(ui_language.t('Gjenopprettingsnøkkelen er ugyldig.')) from None
                if key is None or not secrets_equal(vault.fingerprint(key),remote['value'].get('check','')):
                    raise ValueError(ui_language.t('Kontopassordet er endret. Bruk gjenopprettingsnøkkelen eller logg inn fra en PC som allerede har innstillingene.')) from None
                updated=self.request('/v1/vault/key',{'revision':remote['revision'],'value':vault.wrap(key,password,user)})
                if updated.get('conflict'):raise ValueError(ui_language.t('Kontonøkkelen ble endret samtidig. Prøv å logge inn igjen.'))
        self.config['vault_key']=protect(vault.b64(key))
    def key(self):
        if not self.config.get('vault_key'):raise ValueError(ui_language.t('Logg ut og inn igjen for å aktivere kryptert synkronisering.'))
        return vault.un64(protect(self.config['vault_key'],True))
    def recovery(self):
        with self.lock:
            if not self.config.get('token'):raise ValueError(ui_language.t('Logg inn først.'))
            return {'text':ui_language.t('HamNavigator – privat gjenopprettingsnøkkel\nKonto: ')+self.config.get('email','')+'\nServer: '+self.config.get('url','')+'\n\nHN1-'+vault.b64(self.key())+ui_language.t('\n\nOppbevar denne filen privat. Nøkkelen kan åpne krypterte innstillinger og passord for kontoen.\n')}
    def to_wire(self,item):
        item=copy.deepcopy(item)
        if item['key'] in vault.PRIVATE_KEYS and item.get('value') is not None:item['value']=vault.seal(self.key(),item['value'],self.config['user']+'|'+item['key'])
        return item
    def from_wire(self,item):
        item=copy.deepcopy(item)
        if item['key'] in vault.PRIVATE_KEYS and item.get('value') is not None:item['value']=vault.open_sealed(self.key(),item['value'],self.config['user']+'|'+item['key'])
        return item
    def read_private(self,path):
        value=json.loads(path.read_text(encoding='utf-8'))
        return json.loads(protect(value['protected'],True)) if isinstance(value,dict) and 'protected' in value else value
    def save_private(self,path,value):atomic(path,{'protected':protect(json.dumps(value,ensure_ascii=False))})
    def view(self):
        note=''
        from settings_transfer import pending_conflicts,read_private as read_settings
        blocked=pending_conflicts(self.folder.parent)
        if self.started_at is not None and time.monotonic()-self.started_at>90:
            note=ui_language.t(' Synkroniseringen tar for lang tid. Nye kontakter er foreløpig ikke bekreftet hentet.')
        if self.config.get('token') and not self.config.get('vault_key'):note=ui_language.t(' Logg inn på nytt for også å synkronisere passord og beskyttede innstillinger.')
        pending_path=self.folder/'settings-pending.json'
        if pending_path.exists():
            ready=set(read_settings(pending_path))-{c['key'] for c in blocked}
            names={'map/preferences':'Map','digital/preferences':'Digital','setting/preferences':'MY SHACK'}
            if ready:note=ui_language.t(' Innstillinger for ')+', '.join(names.get(k,'programmet') for k in sorted(ready))+ui_language.t(' brukes ved neste oppstart.')
        if blocked:note+=' '+str(len(blocked))+ui_language.t(' innstillingsgrupper trenger et valg nedenfor. Andre innstillinger behandles uavhengig.')
        if (self.folder/'settings-error.txt').exists():note=' '+(self.folder/'settings-error.txt').read_text(encoding='utf-8')
        conflicts={c['key']:c for c in self.status.get('conflicts',[])}
        for conflict in blocked:conflicts.setdefault(conflict['key'],conflict)
        return {**self.status,'authorized':self.authorized,'admin':self.authorized and self.is_admin,'conflicts':list(conflicts.values()),'message':self.status['message']+note,'url':self.config.get('url',''),'email':self.config.get('email',''),'certificate':self.config.get('certificate',''),'automatic':self.config.get('automatic',False),'connected':bool(self.config.get('token')),'backup_folder':str(self.folder/'backups')}
    def connect(self,data):
        with self.lock:
            password=data.get('password','')
            if not isinstance(password,str) or not password or len(password)>256:raise ValueError(ui_language.t('Skriv passordet ditt (maksimalt 256 tegn).'))
            if data.get('register'):
                if len(password)<12:raise ValueError(ui_language.t('Passordet må ha minst 12 tegn.'))
                if password!=data.get('password_confirm',password):raise ValueError(ui_language.t('Passordene er ikke like.'))
            previous=self.config.copy()
            self.config=self.connection_settings(data)
            try:
                result=self.request('/v1/register' if data.get('register') else '/v1/login',{'email':data.get('email',''),'password':data.get('password',''),'invite':data.get('invite','')})
                if result.get('verification_required'):
                    self.config=previous
                    return {**self.view(),**result,'connected':False}
                self.config.update(email=result['email'],user=result['user'],token=protect(result['token']),automatic=False)
                self.configure_vault(password,str(data.get('recovery','')),previous)
                atomic(self.folder/'connection.json',self.config)
                self.authorized=True;self.is_admin=False;self.last_presence=0
                self.status={'message':(ui_language.t('Kontoen er opprettet. ') if data.get('register') else '')+ui_language.t('Logget inn som ')+result['email']+ui_language.t('. Trykk Synkroniser nå for å dele loggboken med kontoen.'),'conflicts':[]}
            except Exception:self.config=previous;raise
            return self.view()
    def email_action(self,action,data):
        paths={'request-reset':'/v1/auth/request-reset','reset-password':'/v1/auth/reset-password','resend-verification':'/v1/auth/resend-verification','verify-email':'/v1/auth/verify-email'}
        if action not in paths:raise ValueError(ui_language.t('Ukjent kontohandling.'))
        config=self.connection_settings(data)
        return self.request(paths[action],{k:data[k] for k in ('email','password','code') if k in data},config=config,authenticated=False)
    def disconnect(self):
        with self.lock:
            try:self.request('/v1/logout',{})
            finally:
                self.authorized=False;self.is_admin=False
                self.config.pop('token',None);self.config['automatic']=False;atomic(self.folder/'connection.json',self.config)
                self.status={'message':ui_language.t('Logget ut lokalt.'),'conflicts':[]}
        return self.view()
    def auto(self,enabled):
        with self.lock:
            if enabled and not self.config.get('token'):raise ValueError(ui_language.t('Logg inn først.'))
            self.config['automatic']=bool(enabled);atomic(self.folder/'connection.json',self.config)
            if enabled:self.wake.set()
        return self.view()
    def deliveries(self):
        with self.lock:
            if not self.config.get('token'):raise ValueError(ui_language.t('Logg inn først.'))
            items=[];offset=0
            while True:
                page=self.request('/v1/delivery/list',{'offset':offset})
                items.extend(page['items'])
                if not page.get('more'):break
                offset=page['offset']
            local=self.snapshot()
            self.status['deliveries']=[{**item,'call':(local.get(item['qso']) or {}).get('CALL',''),'date':(local.get(item['qso']) or {}).get('QSO_DATE',''),'time':(local.get(item['qso']) or {}).get('TIME_ON','')} for item in items]
            return self.view()
    def sync(self,choices=None):
        with self.lock:
            self.started_at=time.monotonic()
            self.status['syncing']=True
            try:
                return self._sync(choices)
            except Exception as error:
                try:self.ops.history.record('Cloud',error)
                except OSError:pass
                if not self.config.get('token'):
                    self.status['message']=ui_language.t('Logg inn for å synkronisere. Lokale kontakter er beholdt.')
                else:
                    retry=ui_language.t(' Prøver igjen automatisk.') if self.config.get('automatic') else ''
                    self.status['message']=ui_language.t('Synkronisering stoppet: ')+str(error)+retry
                raise
            finally:
                self.status['syncing']=False
                self.started_at=None
                self.last_finished=time.monotonic()

    def _sync(self,choices=None):
        with self.lock:
            if not self.config.get('token'):raise ValueError(ui_language.t('Logg inn først.'))
            namespace=hashlib.sha256((self.config['url']+'|'+self.config['user']).encode()).hexdigest()
            cache=self.folder/(namespace+'.json')
            previous=self.read_private(cache) if cache.exists() else {}
            captured=self.snapshot()
            local=canonical_objects(captured)
            # Legacy accounts can continue syncing their log before vault enrollment.
            # Never replace or remove encrypted settings when this PC lacks the key.
            private_available=bool(self.config.get('vault_key'))
            if not private_available:local={key:value for key,value in local.items() if key not in vault.PRIVATE_KEYS}
            stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            backup=self.folder/'backups'/namespace/(stamp+'.json')
            digest=hashlib.sha256(json.dumps(local,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            if self.backup_digest!=(namespace,digest):
                self.save_private(backup,{'format':1,'data':local})
                self.backup_digest=(namespace,digest)
            # Local dated snapshots are independent of synced deletions. Retain latest 100.
            for old in sorted(backup.parent.glob('*.json'))[:-100]:old.unlink()
            from sync_cursor import pull
            remote_path=self.folder/(namespace+'-remote.json')
            saved_remote=self.read_private(remote_path) if remote_path.exists() else {}
            marker=vault.fingerprint(self.key()) if private_available else 'contacts-only'
            def decode_remote(item):
                if item['key']=='setting/vault-key':return None
                if not private_available and item['key'] in vault.PRIVATE_KEYS:return None
                item=self.from_wire(item)
                if item['key'].startswith('qso/'):item['value']=canonical(item['value'])
                return item
            remote_state,downloaded=pull(self.request,saved_remote,marker,decode_remote,
                force=namespace not in self.cursor_sessions and not saved_remote.get('epoch'))
            remote=remote_state['objects']
            pending=[];incoming={};conflicts=[];baseline=copy.deepcopy(previous);sent=0;merged_contacts=0
            from settings_transfer import pending_conflicts,discard_pending
            blocked={c['key']:c for c in pending_conflicts(self.folder.parent)}
            accepted_local=set()
            def accepted(item):
                return {**item,'sync_schema':2}
            for key in sorted(set(local)|set(previous)|set(remote)):
                if not private_available and key in vault.PRIVATE_KEYS:continue
                old=previous.get(key);r=remote.get(key,{'value':None,'revision':0});value=local.get(key)
                old_value=canonical(old['value']) if old and key.startswith('qso/') else old['value'] if old else None
                choice=(choices or {}).get(key)
                if choice not in (None,'local','cloud'):raise ValueError(ui_language.t('Ugyldig konfliktvalg.'))
                if key in blocked and choice is None:
                    conflicts.append(blocked[key]);continue
                if choice=='cloud':
                    incoming[key]=r['value'];baseline[key]=accepted(r);continue
                if choice=='local':
                    if value!=r['value']:pending.append({'key':key,'value':value,'revision':r['revision']})
                    else:baseline[key]=accepted(r);accepted_local.add(key)
                    continue
                # A fresh/restored server has no deletion tombstone. Preserve the
                # local contact/settings even when an older cache remembers it.
                if key not in remote and value is not None:
                    pending.append({'key':key,'value':value,'revision':0})
                    continue
                if key=='map/preferences' and isinstance(value,dict) and isinstance(r['value'],dict):
                    from settings_merge import merge_map, MISSING as NO_SETTINGS_BASE
                    merged,fields=merge_map(value,r['value'],old_value if old else NO_SETTINGS_BASE)
                    if fields:
                        conflicts.append({'key':key,'local':value,'cloud':r['value'],'fields':fields});continue
                    if merged!=value:incoming[key]=merged
                    if merged!=r['value']:pending.append({'key':key,'value':merged,'revision':r['revision']})
                    else:baseline[key]=accepted(r)
                    continue
                if key.startswith('qso/') and isinstance(value,dict) and isinstance(r['value'],dict) and choice!='local':
                    base=old_value if old and old.get('sync_schema')==2 else MISSING
                    merged,fields=contact_merge(value,r['value'],base)
                    if fields:
                        conflicts.append({'key':key,'local':value,'cloud':r['value'],'fields':fields});continue
                    if merged!=value:incoming[key]=merged
                    if merged!=r['value']:pending.append({'key':key,'value':merged,'revision':r['revision']})
                    else:baseline[key]=accepted(r)
                    if value!=r['value']:merged_contacts+=1
                    continue
                changed=(value != old_value) if old else key in local
                if changed and value!=r['value']:
                    # Revision renumbering after migration/server restore is not a content edit.
                    if r['revision'] and (not old or r['value']!=old_value):
                        if choice!='local':conflicts.append({'key':key,'local':value,'cloud':r['value']});continue
                    pending.append({'key':key,'value':value,'revision':r['revision']})
                else:
                    if value!=r['value']:incoming[key]=r['value']
                    baseline[key]=accepted(r)
            for pos in range(0,len(pending),100):
                reply=self.request('/v1/push',{'items':[self.to_wire(item) for item in pending[pos:pos+100]]})
                for result in reply['items']:
                    result=self.from_wire(result)
                    if result['key'].startswith('qso/'):result['value']=canonical(result['value'])
                    remote[result['key']]=copy.deepcopy(result)
                    if result.get('conflict'):
                        incoming.pop(result['key'],None)
                        conflicts.append({'key':result['key'],'local':local.get(result['key']),'cloud':result['value']})
                    else:
                        baseline[result['key']]=accepted(result);sent+=1
                        if (choices or {}).get(result['key'])=='local':accepted_local.add(result['key'])
            # Callback checks the current local value, preventing concurrent UI edits being lost.
            applied=self.apply(incoming,captured)
            for key in incoming:
                if key not in applied:
                    if key in previous:baseline[key]=previous[key]
                    else:baseline.pop(key,None)
                    conflicts.append({'key':key,'local':ui_language.t('Endret under synkronisering'),'cloud':incoming[key]})
            self.save_private(cache,baseline)
            self.save_private(remote_path,remote_state)
            self.cursor_sessions.add(namespace)
            discard_pending(self.folder.parent,accepted_local)
            conflicts=[{**c,'local':ui_language.t('Beskyttede innstillinger på denne PC-en'),'cloud':ui_language.t('Beskyttede innstillinger i Cloud')} if c['key'] in vault.PRIVATE_KEYS else c for c in conflicts]
            count=sum(key.startswith('qso/') for key in set(local)|set(remote) if local.get(key) is not None or remote.get(key,{}).get('value') is not None)
            message=(ui_language.t('Synkronisering delvis fullført.') if conflicts else 'Synkronisert.')+f" {count}{ui_language.t(' kontakter kontrollert. ')}{sent}{ui_language.t(' endringer sendt, ')}{len(applied)} hentet."
            if merged_contacts:message+=f"{ui_language.t(' Opplysninger for ')}{merged_contacts}{ui_language.t(' kontakter ble samordnet automatisk.')}"
            if conflicts:message+=f" {len(conflicts)}{ui_language.t(' ulike endringer trenger et valg.')}"
            self.config['last_sync_epoch']=time.time();atomic(self.folder/'connection.json',self.config)
            self.status.update(message=message,last_sync=stamp,conflicts=conflicts,merged_contacts=merged_contacts,downloaded_records=downloaded)
            return self.view()
    def start(self):
        if self.worker and self.worker.is_alive():return
        def work():
            while not self.stop.is_set():
                if time.monotonic()-self.last_presence>=30:
                    try:self.presence()
                    except Exception as exc:
                        if not self.authorized:self.status['message']=str(exc)
                if self.config.get('automatic') and self.authorized:
                    try:self.sync()
                    except Exception:pass  # sync retains the error for the UI.
                if self.authorized:
                    try:
                        from log_delivery import Outbox
                        Outbox(self).tick()
                    except Exception as error:
                        try:self.ops.history.record(ui_language.t('Loggtjenester'),error)
                        except OSError:pass
                self.wake.wait(10)
                self.wake.clear()
        self.worker=threading.Thread(target=work,daemon=True,name='HamNavigatorCloud')
        self.worker.start()
