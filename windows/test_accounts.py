import copy,json,ssl,tempfile,threading,unittest,importlib.util
from pathlib import Path
import account_vault as vault
import settings_transfer as transfer
from settings_merge import encode,decode
from cloud_sync import Sync,protect
from test_cloud import server

class Accounts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=server.Store(self.root/'cloud.db')
        spec=importlib.util.spec_from_file_location('cfg',Path(__file__).parent.parent/'cloud-server/configure.py');cfg=importlib.util.module_from_spec(spec);spec.loader.exec_module(cfg);cfg.configure(self.root,['localhost','127.0.0.1'])
        self.web=server.Server(('127.0.0.1',0),self.store);self.web.tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);self.web.tls.load_cert_chain(self.root/'server.crt',self.root/'server.key')
        self.thread=threading.Thread(target=self.web.serve_forever,daemon=True);self.thread.start()
        self.login={'url':f'https://127.0.0.1:{self.web.server_port}','certificate':str(self.root/'server.crt'),'email':'one@example.test','password':'a long test password'}
    def tearDown(self):self.web.shutdown();self.web.server_close();self.thread.join();self.temp.cleanup()
    def client(self,name):
        state={}
        def apply(changes,captured):
            for k,v in changes.items():
                if v is None:state.pop(k,None)
                else:state[k]=copy.deepcopy(v)
            return list(changes)
        return Sync(self.root/name,lambda:copy.deepcopy(state),apply),state
    def test_open_registration_validation_and_isolation(self):
        a,av=self.client('a');self.assertEqual(a.check_connection(self.login)['registration'],'open')
        with self.assertRaises(ValueError):a.connect({**self.login,'register':True,'password':'short'})
        with self.assertRaises(ValueError):a.connect({**self.login,'register':True,'password_confirm':'different'})
        self.assertTrue(a.connect({**self.login,'register':True})['connected'])
        with self.assertRaises(ValueError):a.connect({**self.login,'register':True})
        av['qso/test']={'CALL':'TEST'};a.sync()
        b,bv=self.client('b');b.connect({**self.login,'register':True,'email':'two@example.test'});b.sync();self.assertNotIn('qso/test',bv)
    def test_private_sync_encryption_and_restart(self):
        a,av=self.client('a');a.connect({**self.login,'register':True});secret='fake-secret-not-for-a-real-service'
        av['map/preferences']=encode({'app-settings.json':{'adifLog':{'text':{'qrzApiKey':secret}}}});a.sync();a.sync()
        with self.store.db() as db:
            rows=' '.join(r[0] for r in db.execute('SELECT value FROM objects'));self.assertNotIn(secret,rows);self.assertIn('AES-256-GCM',rows)
        for f in a.folder.rglob('*.json'):self.assertNotIn(secret,f.read_text())
        b,bv=self.client('b');b.connect(self.login);b.sync();self.assertEqual(decode(bv['map/preferences'])['app-settings.json']['adifLog']['text']['qrzApiKey'],secret)
        restarted=Sync(a.folder.parent,lambda:copy.deepcopy(av),a.apply);self.assertEqual(restarted.sync()['conflicts'],[])
        bv['map/preferences']=encode({'app-settings.json':{'adifLog':{'text':{'qrzApiKey':'other'}}}});av['map/preferences']=encode({'app-settings.json':{'adifLog':{'text':{'qrzApiKey':'local'}}}});a.sync();status=b.sync();self.assertEqual(len(status['conflicts']),1);self.assertNotIn('other',json.dumps(status))
        b.sync({'map/preferences':'cloud'});self.assertEqual(bv,av)
    def test_password_reset_recovery_and_invalid_session(self):
        a,av=self.client('a');a.connect({**self.login,'register':True});key='HN1-'+vault.b64(a.key());av['map/preferences']={'password':'retained'};a.sync()
        user=a.config['user'];new='a different strong password';salt='11'*16
        with self.store.db() as db:db.execute('UPDATE users SET salt=?,password=? WHERE id=?',(salt,server.password_hash(new,salt),user));db.execute('DELETE FROM sessions WHERE user=?',(user,))
        with self.assertRaises(ValueError):a.verify()
        self.assertFalse(a.view()['connected'])
        b,bv=self.client('b')
        with self.assertRaisesRegex(ValueError,'Gjenopprettings|gjenopprettings'):b.connect({**self.login,'password':new})
        b.connect({**self.login,'password':new,'recovery':key});b.sync();self.assertEqual(bv['map/preferences']['password'],'retained')
        c,cv=self.client('c');c.connect({**self.login,'password':new});c.sync();self.assertEqual(cv,bv)
    def test_connection_file_and_tamper(self):
        a,av=self.client('a');value={'format':'hamnavigator-cloud','version':1,'url':self.login['url'],'certificate':(self.root/'server.crt').read_text()}
        result=a.import_connection({'text':json.dumps(value)});self.assertEqual(result['registration'],'open');self.assertFalse(a.view()['connected'])
        with self.assertRaises(ValueError):a.import_connection({'text':json.dumps({**value,'certificate':'PRIVATE KEY'})})
        key=b'1'*32;record=vault.seal(key,{'test':1},'one')
        with self.assertRaises(ValueError):vault.open_sealed(key,record,'two')
    def test_settings_stage_retains_logs_and_checks_concurrent_changes(self):
        root=self.root/'app';data=self.root/'profile';data.mkdir();state={'settings':{'call':'TEST','udp_port':2238},'qsos':[{'CALL':'KEEP'}]};(data/'data.json').write_text(json.dumps(state))
        settings={'udp_port':9999};transfer.stage('setting/preferences',settings,root,data,state['settings']);self.assertEqual(transfer.snapshot(root,data,state['settings'])['setting/preferences'],settings)
        transfer.apply_pending(root,data);saved=json.loads((data/'data.json').read_text());self.assertEqual(saved['qsos'],state['qsos']);self.assertEqual(saved['settings']['udp_port'],9999)
        transfer.stage('setting/preferences',{'udp_port':1111},root,data,saved['settings']);saved['settings']['udp_port']=2222;(data/'data.json').write_text(json.dumps(saved))
        self.assertEqual(transfer.apply_pending(root,data)['blocked'],['setting/preferences'])
        self.assertEqual(json.loads((data/'data.json').read_text())['settings']['udp_port'],2222)
    def test_map_and_digital_password_files_transfer_with_local_paths_preserved(self):
        import base64
        aroot=self.root/'a/app';adata=self.root/'a/profile';broot=self.root/'b/app';bdata=self.root/'b/profile'
        for root,data in ((aroot,adata),(broot,bdata)):
            data.mkdir(parents=True);(data/'data.json').write_text(json.dumps({'settings':{},'qsos':[],'repeaters':[]}))
            transfer.folder('digital/preferences',root,data).mkdir(parents=True);transfer.folder('map/preferences',root,data).mkdir(parents=True)
        original={'adifLog':{'text':{'password':'test-secret','apiKey':'test-key'}},'appLogs':[{'file':'a-local-log'}],'trustedQsl':{'binaryFile':'a-local-tqsl'}}
        amap=transfer.folder('map/preferences',aroot,adata)/'app-settings.json';amap.write_text(json.dumps(original))
        bmap=transfer.folder('map/preferences',broot,bdata)/'app-settings.json';bmap.write_text(json.dumps({'appLogs':[{'file':'b-local-log'}],'trustedQsl':{'binaryFile':'b-local-tqsl'}}))
        for name in transfer.FILES['digital/preferences']:(transfer.folder('digital/preferences',aroot,adata)/name).write_bytes(b'test-password=example\r\nlegacy-byte=\xff')
        records=transfer.snapshot(aroot,adata,{})
        for key in ('map/preferences','digital/preferences'):transfer.stage(key,records[key],broot,bdata,{})
        transfer.apply_pending(broot,bdata)
        result=json.loads(bmap.read_text());self.assertEqual(result['adifLog'],original['adifLog']);self.assertEqual(result['appLogs'][0]['file'],'b-local-log');self.assertEqual(result['trustedQsl']['binaryFile'],'b-local-tqsl')
        for name in transfer.FILES['digital/preferences']:self.assertEqual((transfer.folder('digital/preferences',aroot,adata)/name).read_bytes(),(transfer.folder('digital/preferences',broot,bdata)/name).read_bytes())
        with self.assertRaises(ValueError):transfer.validate('digital/preferences',{'../server.py':base64.b64encode(b'bad').decode()})

if __name__=='__main__':unittest.main()
