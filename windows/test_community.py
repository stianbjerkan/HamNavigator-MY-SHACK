import contextlib
import io
import json
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import community

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'cloud-server'))
from admin_users import public_counts


class Counts(unittest.TestCase):
    def test_distinct_verified_unexpired_and_recent(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript('''CREATE TABLE users(id INTEGER, verified INTEGER, disabled INTEGER);
            CREATE TABLE sessions(hash TEXT,user INTEGER,expires REAL);
            CREATE TABLE presence(session TEXT,seen REAL);
            INSERT INTO users VALUES(1,1,0),(2,1,0),(3,0,0),(4,1,1),(5,1,0);''')
        now = time.time()
        for key, user, expiry, seen in [('a',1,now+60,now),('b',1,now+60,now),('c',2,now+60,now-121),('d',3,now+60,now),('e',4,now+60,now),('f',5,now-1,now)]:
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(key,user,expiry))
            db.execute('INSERT INTO presence VALUES(?,?)',(key,seen))
        class Store:
            def db(self): return contextlib.nullcontext(db)
        self.assertEqual(public_counts(Store()), {'registered':5,'active':1})
        db.execute('DELETE FROM sessions WHERE user=1')
        self.assertEqual(public_counts(Store())['active'],0)
        db.execute('DELETE FROM users')
        self.assertEqual(public_counts(Store()), {'registered':0,'active':0})

    def test_validation_and_private_data_removed(self):
        data={'available':True,'registered':12,'active':2,'sample_age':1,'active_seconds':120,'email':'private@example.test'}
        self.assertNotIn('email',community.validate(data))
        for bad in ({'active':True},{'active':13},{'registered':-1},{'sample_age':76},{'active_seconds':30}):
            with self.assertRaises(ValueError): community.validate({**data,**bad})
        self.assertEqual(community.validate({'available':False}),{'available':False})

    def test_cache_failure_and_no_credentials(self):
        community._until=0
        data={'available':True,'registered':12,'active':2,'sample_age':1,'active_seconds':120}
        with patch.object(community.urllib.request,'build_opener') as factory:
            opener=factory.return_value
            opener.open.return_value=io.BytesIO(json.dumps(data).encode())
            self.assertEqual(community.snapshot()['active'],2)
            self.assertEqual(community.snapshot()['registered'],12)
            self.assertEqual(opener.open.call_count,1)
            request=opener.open.call_args.args[0]
            self.assertFalse(request.has_header('Authorization'))
            self.assertFalse(request.has_header('Cookie'))
            community._until=0
            opener.open.side_effect=OSError('offline')
            self.assertEqual(community.snapshot(),{'available':False})


if __name__=='__main__': unittest.main()
