import base64,copy,json,sqlite3,time,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from test_accounts import Accounts
from cloud_sync import Sync
from admin_users import grant
from server import Store
import server_update
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

class AdminTests(Accounts):
    # Reuse only isolated HTTPS fixture, not the inherited account test suite.
    def test_owner_authorization_presence_and_revoke(self):
        a,_=self.client('owner');a.connect({**self.login,'register':True})
        a.verify();self.assertFalse(a.view()['admin']);self.assertTrue(a.authorized)
        with self.assertRaises(ValueError):a.request('/v1/admin/users',{})
        grant(self.store,self.login['email'],True);a.verify();self.assertTrue(a.view()['admin'])
        b,_=self.client('phone');b.connect(self.login);b.request('/v1/account/me',{'client':{'platform':'Android','version':'0.4.4'}})
        c,_=self.client('other');c.connect({**self.login,'register':True,'email':'other@example.test','admin':True});c.verify()
        with self.assertRaises(ValueError):c.request('/v1/admin/users',{})
        result=a.admin_users({});self.assertEqual(result['summary']['total'],2);self.assertEqual(result['summary']['active'],2)
        owner=next(r for r in result['items'] if r['email']==self.login['email'])
        self.assertEqual(owner['active_sessions'],2);self.assertIn('Android 0.4.4',owner['clients'])
        self.assertNotIn('token',json.dumps(result));self.assertNotIn('salt',json.dumps(result))
        with self.store.db() as db:db.execute('UPDATE presence SET seen=?',(time.time()-180,))
        result=a.admin_users({'active_only':True});self.assertEqual(result['summary']['active'],1);self.assertEqual(len(result['items']),1)
        grant(self.store,self.login['email'],False)
        with self.assertRaises(ValueError):a.request('/v1/admin/users',{})
        a.verify();self.assertFalse(a.view()['admin'])
        with self.store.db() as db:db.execute('UPDATE users SET disabled=1 WHERE email=?',(self.login['email'],))
        with self.assertRaises(ValueError):a.verify()
        self.assertFalse(a.authorized);self.assertFalse(a.view()['connected'])

    def test_restart_requires_confirmation_without_erasing_data(self):
        a,av=self.client('owner');a.connect({**self.login,'register':True});av['qso/test']={'CALL':'LA1ABC'};a.sync()
        restarted=Sync(a.folder.parent,a.snapshot,a.apply)
        self.assertFalse(restarted.authorized);self.assertTrue(restarted.view()['connected'])
        with patch.object(restarted,'request',side_effect=ValueError('offline')):
            with self.assertRaises(ValueError):restarted.verify()
        self.assertFalse(restarted.authorized);self.assertIn('qso/test',av)
        restarted.verify();self.assertTrue(restarted.authorized)
        with patch.object(restarted,'request',side_effect=ValueError('offline')):
            with self.assertRaises(ValueError):restarted.presence()
        self.assertTrue(restarted.authorized) # A temporary outage does not cut off an operating radio.
        restarted.disconnect();self.assertFalse(restarted.authorized)

    def test_logout_pagination_and_legacy_migration(self):
        a,_=self.client('owner');a.connect({**self.login,'register':True});grant(self.store,self.login['email'],True);a.verify()
        with self.store.db() as db:
            for i in range(105):db.execute('INSERT INTO users(id,email,salt,password,verified) VALUES(?,?,?,?,1)',(str(i),'u%03d@example.test'%i,'salt','unusable'))
        first=a.admin_users({});second=a.admin_users({'offset':100})
        self.assertTrue(first['more']);self.assertFalse(second['more']);self.assertEqual(len(second['items']),6)
        self.assertFalse(set(r['email'] for r in first['items'])&set(r['email'] for r in second['items']))
        self.assertEqual(a.admin_users({'search':'%'})['items'],[])
        with self.assertRaises(ValueError):a.admin_users({'offset':-1})
        a.disconnect()
        with self.store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM presence').fetchone()[0],0)
        legacy=self.root/'legacy.db'
        with sqlite3.connect(legacy) as db:
            db.executescript("CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT UNIQUE,salt TEXT,password TEXT,disabled INTEGER DEFAULT 0); INSERT INTO users VALUES('old','old@example.test','salt','hash',0);")
        db.close()
        migrated=Store(legacy);Store(legacy)
        with migrated.db() as db:
            row=dict(db.execute('SELECT * FROM users').fetchone());self.assertEqual(row['password'],'hash');self.assertEqual(row['admin'],0)

    def test_private_update_signature_and_download_checksum(self):
        key=Ed25519PrivateKey.generate();public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
        payload={'product':'HamNavigator Cloud','version':'99.0.0','size':3,'sha256':__import__('hashlib').sha256(b'exe').hexdigest()}
        raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
        envelope={'release':payload,'signature':base64.b64encode(key.sign(raw)).decode()}
        from io import BytesIO
        class Opener:
            def __init__(self,data):self.data=data;self.routes=[]
            def open(self,req,timeout):
                self.routes.append(req.full_url)
                return BytesIO(json.dumps(envelope).encode() if req.full_url.endswith('/update') else self.data)
        folder=self.root/'updater';folder.mkdir();(folder/'internet.json').write_text(json.dumps({'url':server_update.URL,'approved':True,'token':'a'*64}))
        with patch.object(server_update,'PUBLIC_KEY',public):
            self.assertEqual(server_update.signed_manifest(envelope),payload)
            bad=copy.deepcopy(envelope);bad['release']['version']='100.0.0'
            with self.assertRaises(Exception):server_update.signed_manifest(bad)
            with patch.object(server_update.urllib.request,'build_opener',return_value=Opener(b'exe')):
                path,_=server_update.fetch(folder);self.assertEqual(path.read_bytes(),b'exe')
            with patch.object(server_update.urllib.request,'build_opener',return_value=Opener(b'bad')):
                with self.assertRaises(ValueError):server_update.fetch(folder)
            self.assertEqual(path.read_bytes(),b'exe');self.assertFalse(list((folder/'updates').glob('*.part')))
        self.assertIsNone(server_update.NoRedirect().redirect_request(None,None,None,None,None,None))

# Do not run Accounts' inherited tests twice from this module.
for name in dir(Accounts):
    if name.startswith('test_'):setattr(AdminTests,name,None)

if __name__=='__main__':unittest.main()
