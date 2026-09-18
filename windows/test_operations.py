import copy,hashlib,json,time,unittest
from unittest.mock import patch
from test_cloud import CloudTests,server
from cloud_sync import Sync
from operations import History
from log_delivery import Outbox,result
from shared_log import dump,identity,parse
from qso_sync import canonical
import deliveries,admin_users

def contact(day='20260914',clock='120000'):
 return {'CALL':'LA1ABC','QSO_DATE':day,'TIME_ON':clock,'BAND':'20M','MODE':'FT8','STATION_CALLSIGN':'LA2ABC','RST_SENT':'-10'}
def key(q):return 'qso/'+hashlib.sha256(json.dumps(identity(q)).encode()).hexdigest()

class OperationsTests(unittest.TestCase):
 setUp=CloudTests.setUp
 tearDown=CloudTests.tearDown
 def client(self,name):
  a,values=CloudTests.client(self,name);a.authorized=True
  def request(path,data):
   if '/delivery/' in path:return deliveries.handle(self.store,self.account['user'],path.rsplit('/',1)[1],data,server.APIError)
   if path.endswith('devices'):return {'items':[]}
   return self.store.pull(self.account['user'],data['after']) if path.endswith('pull') else self.store.push(self.account['user'],data['items'])
  a.request=request;return a,values
 def job(self,box,q):return box.enqueue({'service':'qrz','profile':'LA2ABC','adif':dump([q]),'request':{'kind':'http','url':'https://logbook.qrz.com/api','body':'KEY=private-canary&ACTION=INSERT&ADIF=old'}})
 def test_backup_preview_additive_account_scoped_and_failure(self):
  a,v=self.client('a');q=contact();other=contact('20260915');older=contact('20260910');v.update({key(q):q,'setting/call':'NEW'});a.sync()
  name='20260914T120000.000Z.json';p=a.folder/'backups'/a.ops.namespace()/name
  a.save_private(p,{'format':1,'data':{key(q):{**q,'RST_SENT':'-20'},key(older):older,'setting/call':'OLD'}})
  v[key(other)]=other;preview=a.ops.preview(name);self.assertEqual((preview['add'],preview['different'],preview['current']),(1,1,2))
  with patch.object(a,'save_private',side_effect=OSError('full')):
   with self.assertRaises(OSError):a.ops.restore(name)
  self.assertNotIn(key(older),v)
  self.assertEqual(a.ops.restore(name)['added'],1);self.assertEqual(v[key(q)]['RST_SENT'],'-10');self.assertEqual(v['setting/call'],'NEW');self.assertIn(key(other),v)
  self.assertEqual(a.ops.restore(name)['added'],0)
  with self.assertRaises(ValueError):a.ops.preview('../'+name)
  a.config['user']='other-account'
  self.assertEqual(a.ops.backup_items()['items'],[])
  with self.assertRaises(ValueError):a.ops.restore(name)
 def test_bad_backup_identity_and_date_rejected(self):
  a,v=self.client('a');q=contact();name='20260914T120000Z.json';p=a.folder/'backups'/a.ops.namespace()/name
  for bad in ({'qso/'+'a'*64:q},{key(contact('20261340')):contact('20261340')}):
   a.save_private(p,{'format':1,'data':bad})
   with self.assertRaises(ValueError):a.ops.restore(name)
   self.assertEqual(v,{})
 def test_history_persists_and_diagnostics_redact(self):
  a,v=self.client('a');secret='password-APIKEY-SECRET-CANARY'
  a.ops.history.record('Cloud',ValueError('https://user:'+secret+'@host.invalid'))
  a.ops.history.record('Cloud',ValueError('https://user:'+secret+'@host.invalid'))
  self.assertEqual(History(a.folder.parent).read()[0]['count'],2)
  text=json.dumps(a.ops.diagnostics())+a.ops.history.path.read_text();self.assertNotIn(secret,text);self.assertNotIn('test@example.test',text)
  self.assertEqual(a.ops.history.read()[0]['code'],'tls')
 def test_pending_live_and_overview_receipt_revision(self):
  a,v=self.client('a');q=contact();v[key(q)]=q;self.assertEqual(a.ops.client()['pending'],1);a.sync();self.assertEqual(a.ops.client()['pending'],0)
  box=Outbox(a);self.job(box,q)
  with patch.object(box,'send',return_value='uncertain'):box.tick()
  view=a.ops.overview();row=view['deliveries'][0];remote=a.request('/v1/delivery/list',{})['items'][0]
  self.assertTrue(row['can_resolve']);self.assertEqual(row['expected'],remote['updated']);self.assertEqual(view['pending'],0)
 def test_two_clients_one_external_send_encrypted_queue(self):
  a,v=self.client('a');b,w=self.client('b');q=contact();v[key(q)]=q;a.sync();b.sync();first=Outbox(a);second=Outbox(b)
  self.job(first,q);self.job(first,q);self.job(second,q)
  self.assertEqual(len(first.rows()),1)
  for f in first.folder().glob('*.json'):self.assertNotIn('private-canary',f.read_text())
  with patch.object(Outbox,'send',return_value='delivered') as send:
   first.tick();second.tick();first.tick();self.assertEqual(send.call_count,1)
  self.assertEqual(second.rows()[0]['state'],'delivered')
 def test_receipt_lost_response_does_not_reupload(self):
  for outcome in ('delivered','retry','rejected','uncertain'):
   a,v=self.client(outcome);q=contact(clock={'delivered':'120001','retry':'120002','rejected':'120003','uncertain':'120004'}[outcome]);v[key(q)]=q;a.sync();box=Outbox(a);self.job(box,q);real=a.request;failed=[False]
   def request(path,data):
    reply=real(path,data)
    if path.endswith('/complete') and not failed[0]:failed[0]=True;raise OSError('lost receipt')
    return reply
   a.request=request
   with patch.object(box,'send',return_value=outcome) as send:
    with self.assertRaises(OSError):box.tick()
    self.assertEqual(box.rows()[0]['state'],'ack');box.tick();self.assertEqual(send.call_count,1);self.assertEqual(box.rows()[0]['state'],outcome)
 def test_crash_after_begin_never_resends_without_owner_choice(self):
  a,v=self.client('a');q=contact();v[key(q)]=q;a.sync();box=Outbox(a);self.job(box,q)
  with patch.object(box,'send',side_effect=SystemExit):
   with self.assertRaises(SystemExit):box.tick()
  self.assertEqual(box.rows()[0]['state'],'sending')
  with patch.object(box,'send') as send:box.tick();box.tick();send.assert_not_called()
  self.assertEqual(box.rows()[0]['state'],'uncertain')
 def test_sending_uses_current_synced_data(self):
  a,v=self.client('a');q=contact();v[key(q)]=q;a.sync();box=Outbox(a);self.job(box,q);v[key(q)]={**q,'COMMENT':'edited'};a.sync()
  def send(job):self.assertEqual(parse(job['adif'])[0]['COMMENT'],'edited');self.assertIn('edited',job['request']['body']);return 'delivered'
  with patch.object(box,'send',side_effect=send):box.tick()
 def test_no_upload_until_synced_and_journal_saved(self):
  a,v=self.client('a');q=contact();box=Outbox(a);self.job(box,q)
  with patch.object(box,'send') as send:box.tick();send.assert_not_called()
  v[key(q)]=q;a.sync()
  with patch.object(box,'save',side_effect=OSError('disk full')),patch.object(box,'send') as send:
   with self.assertRaises(OSError):box.tick()
   send.assert_not_called()
 def test_truthful_results(self):
  self.assertEqual(result('qrz',200,'RESULT=OK'),'delivered');self.assertEqual(result('clublog',200,'QSO Duplicate'),'delivered')
  for service in ('qrz','clublog','eqsl','lotw','cloudlog','hrdlog','hamcq'):self.assertEqual(result(service,200,'<html>OK</html>'),'uncertain')
  self.assertEqual(result('qrz',429,''),'retry');self.assertEqual(result('qrz',403,''),'rejected')

class DeliveryExtensionTests(unittest.TestCase):
 setUp=CloudTests.setUp
 tearDown=CloudTests.tearDown
 def test_queue_owner_resolution_cas_and_sent_receipt(self):
  q=contact();k=key(q);self.store.push(self.account['user'],[{'key':k,'value':q,'revision':0}]);args={'qso':k,'service':'lotw','profile':'LA2ABC','payload':hashlib.sha256(json.dumps(q,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
  def call(action,**extra):return deliveries.handle(self.store,self.account['user'],action,{**args,**extra},server.APIError)
  self.assertEqual(call('queue')['state'],'queued')
  with self.assertRaises(server.APIError):call('begin',ticket='')
  ticket=call('claim')['ticket'];call('begin',ticket=ticket);call('complete',ticket=ticket,state='uncertain');row=call('queue')
  with self.assertRaises(server.APIError):call('account-resolve',state='retry',checked=True,expected=0)
  call('account-resolve',state='retry',checked=True,expected=row['updated'])
  with self.assertRaises(server.APIError):call('account-resolve',state='retry',checked=True,expected=row['updated'])
  ticket=call('claim')['ticket'];call('begin',ticket=ticket);call('complete',ticket=ticket,state='sent');self.assertFalse(call('claim')['allowed']);self.assertEqual(call('claim')['state'],'sent')
  other=self.store.register({'email':'other@example.test','password':'a strong test password','invite':self.store.invite()})
  with self.assertRaises(server.APIError):deliveries.handle(self.store,other['user'],'account-resolve',{**args,'state':'retry','checked':True,'expected':row['updated']},server.APIError)
 def test_device_account_isolation_and_login_deduplication(self):
  session=hashlib.sha256(self.account['token'].encode()).hexdigest();device='a'*32
  admin_users.touch(self.store,session,{'device':device,'name':'PC <one>','platform':'Windows','version':'1.9.11','last_sync':time.time(),'pending':2})
  second=self.store.login({'email':'test@example.test','password':'a strong test password'});sid=hashlib.sha256(second['token'].encode()).hexdigest()
  admin_users.touch(self.store,sid,{'device':device,'name':'PC one','platform':'Windows','version':'1.9.11','pending':float('nan')})
  result=admin_users.devices(self.store,self.account['user'],sid);self.assertEqual(len(result['items']),1);self.assertTrue(result['items'][0]['current']);self.assertEqual(result['items'][0]['pending'],0)
  self.assertNotIn(session,json.dumps(result));self.assertNotIn(self.account['token'],json.dumps(result));self.assertEqual(admin_users.devices(self.store,'other-account',sid)['items'],[])

if __name__=='__main__':unittest.main()
