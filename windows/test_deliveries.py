import hashlib, importlib.util, json, sys, threading, unittest
from pathlib import Path
import test_cloud
server=test_cloud.server

spec=importlib.util.spec_from_file_location('deliveries',Path(__file__).parent.parent/'cloud-server/deliveries.py')
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)
sys.modules['deliveries']=delivery

class DeliveryTests(unittest.TestCase):
    tearDown=test_cloud.CloudTests.tearDown
    def setUp(self):
        test_cloud.CloudTests.setUp(self)
        self.key='qso/'+'a'*64
        self.value={'CALL':'LA1ABC','QSO_DATE':'20260910','TIME_ON':'120000'}
        self.store.push(self.account['user'],[{'key':self.key,'value':self.value,'revision':0}])
        payload=hashlib.sha256(json.dumps(self.value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.args={'qso':self.key,'service':'qrz','profile':'LB7YK','payload':payload}
    def call(self,action,**extra):
        return delivery.handle(self.store,self.account['user'],action,{**self.args,**extra},server.APIError)
    def test_delete_account_authenticated_and_isolated(self):
        self.call('claim')
        other=self.store.register({'email':'keep@example.test','password':'a strong test password','invite':self.store.invite()})
        self.store.push(other['user'],[{'key':'qso/keep','value':{'CALL':'LA2ABC'},'revision':0}])
        with self.assertRaises(server.APIError):self.store.delete_account(self.account['user'],{'confirm':'DELETE','password':'wrong'})
        self.assertEqual(self.store.user(self.account['token']),self.account['user'])
        with self.assertRaises(server.APIError):self.store.delete_account(self.account['user'],{'password':'a strong test password'})
        self.store.delete_account(self.account['user'],{'confirm':'DELETE','password':'a strong test password'})
        with self.assertRaises(server.APIError):self.store.user(self.account['token'])
        self.assertEqual(self.store.user(other['token']),other['user'])
        self.assertEqual(len(self.store.pull(other['user'],0)['items']),1)
        with self.store.db() as db:
            for table in ('sessions','objects','changes','deliveries'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table+' WHERE user=?',(self.account['user'],)).fetchone()[0],0)
    def test_two_devices_only_one_permission(self):
        barrier=threading.Barrier(2);results=[]
        def claim():barrier.wait();results.append(self.call('claim'))
        a=threading.Thread(target=claim);b=threading.Thread(target=claim);a.start();b.start();a.join();b.join()
        self.assertEqual(sum(r['allowed'] for r in results),1)
        ticket=next(r['ticket'] for r in results if r['allowed'])
        with self.assertRaises(server.APIError):self.call('begin',ticket='wrong')
        self.call('begin',ticket=ticket)
        self.call('complete',ticket=ticket,state='delivered')
        self.assertEqual(self.call('claim')['state'],'delivered')
        self.assertFalse(self.call('claim')['allowed'])
        self.call('complete',ticket=ticket,state='delivered')
    def test_crash_after_begin_never_retries(self):
        ticket=self.call('claim')['ticket'];self.call('begin',ticket=ticket)
        with self.store.db() as db:db.execute('UPDATE deliveries SET until=0')
        self.assertEqual(self.call('claim')['state'],'uncertain')
        self.assertFalse(self.call('claim')['allowed'])
        self.call('complete',ticket=ticket,state='delivered')
        self.assertEqual(self.call('list')['items'][0]['state'],'delivered')
    def test_expired_reservation_and_changed_contact(self):
        old=self.call('claim')['ticket']
        with self.store.db() as db:db.execute('UPDATE deliveries SET until=0')
        new=self.call('claim')['ticket'];self.assertNotEqual(new,old)
        with self.assertRaises(server.APIError):self.call('begin',ticket=old)
        revision=self.store.pull(self.account['user'],0)['items'][0]['revision']
        self.store.push(self.account['user'],[{'key':self.key,'value':{**self.value,'COMMENT':'Changed'},'revision':revision}])
        with self.assertRaises(server.APIError):self.call('begin',ticket=new)
    def test_account_isolation_for_delivery(self):
        self.call('claim')
        other=self.store.register({'email':'second@example.test','password':'a strong test password','invite':self.store.invite()})
        self.assertEqual(delivery.handle(self.store,other['user'],'list',{},server.APIError)['items'],[])
        with self.assertRaises(server.APIError):delivery.handle(self.store,other['user'],'claim',self.args,server.APIError)
    def test_completion_before_begin_refused_and_secret_not_public(self):
        ticket=self.call('claim')['ticket']
        with self.assertRaises(server.APIError):self.call('complete',ticket=ticket,state='delivered')
        self.assertNotIn(ticket,json.dumps(self.call('list')))
    def test_profile_case_and_manual_resolution(self):
        ticket=self.call('claim',profile='lb7yk')['ticket']
        self.assertFalse(self.call('claim',profile='LB7YK')['allowed'])
        self.call('begin',ticket=ticket)
        with self.assertRaises(server.APIError):self.call('resolve',ticket=ticket,state='retry',checked=True)
        self.call('complete',ticket=ticket,state='uncertain')
        with self.assertRaises(server.APIError):self.call('resolve',ticket=ticket,state='retry')
        self.call('resolve',ticket=ticket,state='retry',checked=True)
        self.assertTrue(self.call('claim')['allowed'])

if __name__=='__main__':unittest.main()
