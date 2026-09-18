import copy
import json
import tempfile
import unittest
from pathlib import Path

from settings_merge import decode,encode,merge_map
import settings_transfer as transfer
import test_accounts


def profile(config):
    return encode({'app-settings.json':config,'windows.json':{'map':{'width':900}}})


EMPTY={'adifLog':{'text':{'qrzApiKey':'','clubCall':'','clubEmail':'','clubPassword':'',
                        'lotwLogin':'','lotwPassword':'','lotwStation':'','lotwTrusted':'',
                        'eQSLUser':'','eQSLPassword':''},
                 'qsolog':{'logQRZqsoCheckBox':False,'logClubqsoCheckBox':False,'logLOTWqsoCheckBox':False,'logeQSLQSOCheckBox':False}},
       'app':{'lookupLoginQrz':'','lookupPasswordQrz':''},'map':{'zoom':4}}
CONFIGURED=copy.deepcopy(EMPTY)
CONFIGURED['adifLog']['text'].update(qrzApiKey='fake-qrz-key',clubCall='TEST',clubEmail='test@example.test',clubPassword='fake-club',
                                    lotwLogin='TEST',lotwPassword='fake-lotw',lotwStation='Home',lotwTrusted='fake-tqsl',eQSLUser='TEST',eQSLPassword='fake-eqsl')
CONFIGURED['adifLog']['qsolog']={key:True for key in EMPTY['adifLog']['qsolog']}
CONFIGURED['app'].update(lookupLoginQrz='TEST',lookupPasswordQrz='fake-lookup')


class MergeTests(unittest.TestCase):
    def test_new_pc_adopts_configured_services_and_switches(self):
        merged,conflicts=merge_map(profile(EMPTY),profile(CONFIGURED))
        self.assertEqual(conflicts,[])
        self.assertEqual(decode(merged)['app-settings.json'],CONFIGURED)

    def test_empty_cloud_cannot_erase_existing_accounts_even_with_baseline(self):
        for base in (profile(EMPTY),profile(CONFIGURED)):
            merged,conflicts=merge_map(profile(CONFIGURED),profile(EMPTY),base)
            self.assertEqual(conflicts,[])
            self.assertEqual(decode(merged)['app-settings.json'],CONFIGURED)

    def test_two_accounts_never_mix_identity_password_or_endpoint(self):
        changed=copy.deepcopy(CONFIGURED)
        changed['adifLog']['text'].update(clubEmail='other@example.test',clubPassword='other-secret')
        merged,conflicts=merge_map(profile(CONFIGURED),profile(changed))
        self.assertIn('ClubLog',conflicts)
        text=decode(merged)['app-settings.json']['adifLog']['text']
        self.assertEqual(text['clubEmail'],CONFIGURED['adifLog']['text']['clubEmail'])
        self.assertEqual(text['clubPassword'],CONFIGURED['adifLog']['text']['clubPassword'])

    def test_password_change_with_known_baseline_and_different_view_settings(self):
        a,b=copy.deepcopy(CONFIGURED),copy.deepcopy(CONFIGURED)
        a['map']['zoom']=8
        b['adifLog']['text']['clubPassword']='new-password'
        merged,conflicts=merge_map(profile(a),profile(b),profile(CONFIGURED))
        self.assertEqual(conflicts,[])
        actual=decode(merged)['app-settings.json']
        self.assertEqual(actual['map']['zoom'],8)
        self.assertEqual(actual['adifLog']['text']['clubPassword'],'new-password')

    def test_pending_empty_copy_cannot_hide_or_clear_original_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'app';data=Path(directory)/'data';data.mkdir()
            logs={'settings':{},'qsos':[{'CALL':'KEEP'}],'repeaters':[]}
            (data/'data.json').write_text(json.dumps(logs))
            folder=transfer.folder('map/preferences',root,data);folder.mkdir(parents=True)
            configured={**CONFIGURED,'appLogs':[{'file':'local.adi'}],'trustedQsl':{'binaryFile':'local-tqsl.exe'}}
            (folder/'app-settings.json').write_text(json.dumps(configured))
            transfer.stage('map/preferences',profile(EMPTY),root,data,{})
            visible=decode(transfer.snapshot(root,data,{})['map/preferences'])['app-settings.json']
            self.assertEqual(visible['adifLog'],CONFIGURED['adifLog'])
            # Map serializes again on exit; unrelated changes must not block passwords.
            configured['map']={'zoom':9}
            (folder/'app-settings.json').write_text(json.dumps(configured,indent=4))
            transfer.apply_pending(root,data)
            saved=json.loads((folder/'app-settings.json').read_text())
            self.assertEqual(saved['adifLog'],CONFIGURED['adifLog'])
            self.assertEqual(saved['appLogs'],configured['appLogs'])
            self.assertEqual(saved['trustedQsl'],configured['trustedQsl'])
            self.assertEqual(saved['map']['zoom'],9)
            self.assertEqual(json.loads((data/'data.json').read_text()),logs)


class FreshDesktopSync(unittest.TestCase):
    setUp=test_accounts.Accounts.setUp
    tearDown=test_accounts.Accounts.tearDown
    # Reuse the isolated HTTPS server and accounts; no real services or radio.
    def test_fresh_defaults_receive_credentials_through_encrypted_cloud_and_restart(self):
        clients=[]
        for name in ('first','second'):
            root=self.root/name/'app';data=self.root/name/'data';data.mkdir(parents=True)
            (data/'data.json').write_text(json.dumps({'settings':{},'qsos':[{'CALL':'KEEP'}],'repeaters':[]}))
            path=transfer.folder('map/preferences',root,data);path.mkdir(parents=True)
            (path/'app-settings.json').write_text(json.dumps(CONFIGURED if name=='first' else EMPTY))
            from cloud_sync import Sync
            def apply(items,captured,r=root,d=data):
                for key,value in items.items():transfer.stage(key,value,r,d,{})
                return list(items)
            client=Sync(data,lambda r=root,d=data:transfer.snapshot(r,d,{}),apply)
            clients.append((client,root,data,path))
        a,_,_,_=clients[0];b,root,data,path=clients[1]
        a.connect({**self.login,'register':True});a.sync()
        b.connect(self.login);self.assertEqual(b.sync()['conflicts'],[])
        transfer.apply_pending(root,data)
        saved=json.loads((path/'app-settings.json').read_text())
        self.assertEqual(saved['adifLog'],CONFIGURED['adifLog'])
        self.assertEqual(saved['app'],CONFIGURED['app'])
        for client,_,_,_ in clients:
            self.assertEqual(client.sync()['conflicts'],[])
            self.assertEqual(client.sync()['conflicts'],[])
        with self.store.db() as db:
            wire=' '.join(row[0] for row in db.execute('SELECT value FROM objects'))
        self.assertIn('AES-256-GCM',wire)
        self.assertNotIn('fake-club',wire)
        self.assertNotIn(profile(CONFIGURED)['app-settings.json'],wire)


if __name__=='__main__':unittest.main()
