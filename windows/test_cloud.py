import copy, importlib.util, json, ssl, tempfile, threading, unittest, urllib.request, sys
from pathlib import Path
from cloud_sync import Sync, protect
sys.path.insert(0,str(Path(__file__).parent.parent/'cloud-server'))

spec=importlib.util.spec_from_file_location('hnserver',Path(__file__).parent.parent/'cloud-server/server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]/'tester');self.root=Path(self.temp.name);self.store=server.Store(self.root/'test.db',registration='invite')
        self.account=self.store.register({'email':'test@example.test','password':'a strong test password','invite':self.store.invite()})
    def tearDown(self):self.temp.cleanup()
    def client(self,name):
        values={}
        def apply(changes,captured):
            for k,v in changes.items():
                if v is None:values.pop(k,None)
                else:values[k]=copy.deepcopy(v)
            return list(changes)
        client=Sync(self.root/name,lambda:copy.deepcopy(values),apply)
        client.config={'url':'https://example.test','user':self.account['user'],'token':'test'}
        client.request=lambda path,data:self.store.pull(self.account['user'],data['after']) if path.endswith('pull') else self.store.push(self.account['user'],data['items'])
        return client,values
    def test_account_isolation_and_invites(self):
        with self.assertRaises(server.APIError):self.store.register({'email':'x@example.test','password':'a strong test password','invite':'invalid'})
        other=self.store.register({'email':'other@example.test','password':'a strong test password','invite':self.store.invite()})
        self.store.push(self.account['user'],[{'key':'qso/a','value':{'CALL':'LA1ABC'},'revision':0}])
        self.assertEqual(self.store.pull(other['user'],0)['items'],[])
        with self.assertRaises(server.APIError):self.store.user('invalid')
        with self.assertRaises(server.APIError):self.store.login({'email':'test@example.test','password':'wrong'})
    def test_two_way_offline_edit_delete_and_conflict(self):
        a,av=self.client('a');b,bv=self.client('b')
        av['qso/a']={'CALL':'LA1ABC'};a.sync();b.sync();self.assertEqual(av,bv)
        bv['qso/b']={'CALL':'LA2ABC'};b.sync();a.sync();self.assertEqual(av,bv)
        av['qso/a']['COMMENT']='PC A';bv['qso/a']['COMMENT']='PC B'
        a.sync();result=b.sync();self.assertEqual(len(result['conflicts']),1);self.assertEqual(bv['qso/a']['COMMENT'],'PC B')
        b.sync({'qso/a':'cloud'});self.assertEqual(av,bv)
        del av['qso/a'];a.sync();b.sync();self.assertNotIn('qso/a',bv)
        self.assertTrue(list((b.folder/'backups').rglob('*.json')))
    def test_idempotent_retry_and_cas(self):
        item={'key':'setting/call','value':'LA1ABC','revision':0}
        first=self.store.push(self.account['user'],[item]);second=self.store.push(self.account['user'],[item]);self.assertEqual(first,second)
        item['value']='LA2ABC';self.assertTrue(self.store.push(self.account['user'],[item])['items'][0]['conflict'])
    def test_restart_and_pagination(self):
        a,av=self.client('a')
        for i in range(205):av['qso/'+str(i)]={'CALL':'LA1ABC','N':str(i)}
        a.sync();b,bv=self.client('b');b.sync();self.assertEqual(av,bv)
        restarted=Sync(a.folder.parent,lambda:copy.deepcopy(av),a.apply);restarted.config=a.config;restarted.request=a.request
        self.assertEqual(restarted.sync()['conflicts'],[])
    def test_conflict_preserves_concurrent_local_edit(self):
        a,av=self.client('a');b,bv=self.client('b');av['setting/call']='LA1ABC';a.sync();b.sync()
        av['setting/call']='LA2ABC';a.sync()
        b.apply=lambda changes,captured:[]
        self.assertEqual(len(b.sync()['conflicts']),1)
        self.assertEqual(bv['setting/call'],'LA1ABC')
    def test_dpapi(self):
        ciphertext=protect('secret-session');self.assertNotIn('secret-session',ciphertext);self.assertEqual(protect(ciphertext,True),'secret-session')
    @unittest.skipUnless(importlib.util.find_spec('radio_assistant'),'Requires MY SHACK source tree')
    def test_my_shack_adapter_preserves_device_fields_and_validates(self):
        import radio_assistant as app
        old_state,old_dir=app.STATE,app.DATA_DIR
        try:
            app.STATE=copy.deepcopy(app.DEFAULTS);app.DATA_DIR=self.root/'adapter';app.DATA_DIR.mkdir()
            app.STATE['settings']['mshv_path']='C:/local/radio.exe'
            snap=app.cloud_snapshot();self.assertNotIn('setting/mshv_path',snap)
            self.assertEqual(app.cloud_apply({'setting/call':'LA1ABC','setting/mshv_path':'bad'},snap),['setting/call'])
            self.assertEqual(app.STATE['settings']['mshv_path'],'C:/local/radio.exe')
            snap=app.cloud_snapshot()
            with self.assertRaises(ValueError):app.cloud_apply({'setting/call':'LA2ABC','qso/a':{'CALL':'invalid'}},snap)
            self.assertEqual(app.STATE['settings']['call'],'LA1ABC')
            layout={'version':1,'arrangement':4,'locked':True,'panels':[{'source':'home'}]+[{'source':None}]*5}
            self.assertIn('panels/layout',app.cloud_apply({'panels/layout':layout},snap))
            self.assertTrue((app.DATA_DIR/'cloud-panels-pending.json').exists())
        finally:app.STATE,app.DATA_DIR=old_state,old_dir
    def test_real_https_login_sync_and_logout(self):
        cspec=importlib.util.spec_from_file_location('configure',Path(__file__).parent.parent/'cloud-server/configure.py')
        module=importlib.util.module_from_spec(cspec);cspec.loader.exec_module(module);module.configure(self.root,['localhost','127.0.0.1'])
        web=server.Server(('127.0.0.1',0),self.store);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.root/'server.crt',self.root/'server.key');web.tls=context
        thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
        try:
            client=Sync(self.root/'https',lambda:{'setting/call':'LA1ABC'},lambda a,b:[])
            result=client.connect({'url':f'https://127.0.0.1:{web.server_port}','certificate':str(self.root/'server.crt'),'email':'test@example.test','password':'a strong test password'})
            self.assertTrue(result['connected']);self.assertEqual(client.sync()['conflicts'],[])
            client.disconnect();self.assertFalse(client.view()['connected'])
        finally:web.shutdown();web.server_close();thread.join()

if __name__=='__main__':unittest.main()
