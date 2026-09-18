import copy
import hashlib
import json
import unittest
from qso_sync import canonical, contact_merge, LOCAL_FIELDS
import test_cloud


class ContactMergeTests(unittest.TestCase):
    def test_equivalent_format_and_machine_metadata(self):
        a={'CALL':'la1abc','BAND':'20m','MODE':'FT8','TIME_ON':'1200','FREQ':'14.074000', 'COMMENT':'', 'APP_HAMNAVIGATOR_ID':'pc-a'}
        b={'CALL':'LA1ABC','BAND':'20M','MODE':'FT8','TIME_ON':'120000','FREQ':'14.074','APP_HAMNAVIGATOR_ID':'pc-b'}
        self.assertEqual(canonical(a),canonical(b))

    def test_first_connection_preserves_complementary_fields(self):
        merged, conflicts=contact_merge({'CALL':'LA1ABC','COMMENT':'Portable'}, {'CALL':'LA1ABC','MY_GRIDSQUARE':'JP53FG'})
        self.assertEqual(conflicts,[])
        self.assertEqual(merged,{'CALL':'LA1ABC','COMMENT':'Portable','MY_GRIDSQUARE':'JP53FG'})

    def test_three_way_disjoint_edits_and_explicit_field_removal(self):
        base={'CALL':'LA1ABC','COMMENT':'old','NAME':'Name'}
        a={**base,'COMMENT':'new'};b={'CALL':'LA1ABC','COMMENT':'old'}
        merged,conflicts=contact_merge(a,b,base)
        self.assertEqual(conflicts,[]);self.assertEqual(merged,{'CALL':'LA1ABC','COMMENT':'new'})

    def test_true_field_conflict_is_not_overwritten(self):
        merged,conflicts=contact_merge({'COMMENT':'A'},{'COMMENT':'B'},{'COMMENT':'old'})
        self.assertEqual(conflicts,['COMMENT']);self.assertNotIn('COMMENT',merged)


class ContactSyncTests(unittest.TestCase):
    setUp=test_cloud.CloudTests.setUp
    tearDown=test_cloud.CloudTests.tearDown
    client=test_cloud.CloudTests.client
    def test_657_legacy_contacts_and_revision_renumbering(self):
        a,av=self.client('legacy-upgrade')
        previous={}
        # Force revision numbers to differ from the previous server's cache.
        self.store.push(self.account['user'],[{'key':'setting/seed','value':'ok','revision':0}])
        for index in range(657):
            key='qso/'+str(index)
            q={'CALL':'LA1ABC','QSO_DATE':'20260902','TIME_ON':f'{index//60:02d}{index%60:02d}00','BAND':'20m','MODE':'FT8'}
            av[key]={**q,'APP_HAMNAVIGATOR_ID':f'local-{index}','APP_HAMNAVIGATOR_NATIVE_ORIGINAL':'original row'}
            remote={**q,'MY_GRIDSQUARE':'JP53FG','GRIDSQUARE':''}
            previous[key]={'key':key,'value':remote,'revision':index+1}
            self.store.push(self.account['user'],[{'key':key,'value':remote,'revision':0}])
        key='panels/layout';remote={'arrangement':1,'locked':True};av[key]={'arrangement':0,'locked':True}
        previous[key]={'key':key,'value':remote,'revision':1}
        self.store.push(self.account['user'],[{'key':key,'value':remote,'revision':0}])
        namespace=hashlib.sha256((a.config['url']+'|'+a.config['user']).encode()).hexdigest()
        a.save_private(a.folder/(namespace+'.json'),previous)
        result=a.sync()
        self.assertEqual(result['conflicts'],[])
        self.assertEqual(sum(k.startswith('qso/') for k in av),657)
        self.assertTrue(all(v.get('MY_GRIDSQUARE')=='JP53FG' for k,v in av.items() if k.startswith('qso/')))
        self.assertEqual(av['panels/layout']['arrangement'],0)
        result=a.sync();self.assertEqual(result['conflicts'],[])
        self.assertIn('0 endringer sendt, 0 hentet',result['message'])

    def test_two_computers_merge_different_fields(self):
        a,av=self.client('a');b,bv=self.client('b')
        av['qso/a']={'CALL':'LA1ABC','COMMENT':'old'};a.sync();b.sync()
        av['qso/a']['COMMENT']='Portable';bv['qso/a']['NAME']='Ole'
        a.sync();self.assertEqual(b.sync()['conflicts'],[]);a.sync()
        self.assertEqual(av,bv);self.assertEqual(av['qso/a']['COMMENT'],'Portable');self.assertEqual(av['qso/a']['NAME'],'Ole')

    def test_same_call_on_different_dates_is_not_deduplicated(self):
        a,av=self.client('a');b,bv=self.client('b')
        av['qso/day1']={'CALL':'LA1ABC','QSO_DATE':'20260901','TIME_ON':'120000'}
        av['qso/day2']={'CALL':'LA1ABC','QSO_DATE':'20260902','TIME_ON':'120000'}
        a.sync();b.sync();self.assertEqual(len(bv),2)

    def test_push_race_does_not_apply_a_stale_automatic_merge(self):
        a,av=self.client('a');b,bv=self.client('b')
        av['qso/a']={'CALL':'LA1ABC'};a.sync();b.sync()
        av['qso/a']['COMMENT']='A';bv['qso/a']['NAME']='B';a.sync()
        request=b.request
        def race(path,data):
            if path.endswith('/push'):
                av['qso/a']['NAME']='Concurrent';a.sync()
            return request(path,data)
        b.request=race
        result=b.sync();self.assertEqual(len(result['conflicts']),1)
        self.assertNotIn('COMMENT',bv['qso/a']);self.assertEqual(bv['qso/a']['NAME'],'B')

    def test_empty_replacement_server_does_not_delete_existing_contacts(self):
        a,av=self.client('a');av['qso/a']={'CALL':'LA1ABC'};av['setting/call']='LA9ABC';a.sync()
        other=test_cloud.server.Store(self.root/'replacement.db',registration='invite')
        user=other.register({'email':'a@example.test','password':'a strong test password','invite':other.invite()})['user']
        a.request=lambda path,data:other.pull(user,data['after']) if path.endswith('pull') else other.push(user,data['items'])
        result=a.sync();self.assertEqual(result['conflicts'],[])
        self.assertEqual(av['qso/a'],{'CALL':'LA1ABC'})
        self.assertEqual(len(other.pull(user,0)['items']),2)

    def test_legacy_login_preserves_encrypted_settings_without_vault_key(self):
        import account_vault as vault
        a,av=self.client('a');key=next(iter(vault.PRIVATE_KEYS))
        av[key]={'local':'keep'};av['qso/a']={'CALL':'LA1ABC'}
        remote={'encrypted':'not-readable-without-key'}
        self.store.push(self.account['user'],[{'key':key,'value':remote,'revision':0}])
        result=a.sync();self.assertEqual(result['conflicts'],[])
        self.assertEqual(av[key],{'local':'keep'})
        actual=next(x for x in self.store.pull(self.account['user'],0)['items'] if x['key']==key)
        self.assertEqual(actual['value'],remote)


if __name__=='__main__':unittest.main()
