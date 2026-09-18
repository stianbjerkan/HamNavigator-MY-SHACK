import copy
import unittest
import test_cloud
server=test_cloud.server


class IncrementalSyncTests(unittest.TestCase):
    setUp=test_cloud.CloudTests.setUp
    tearDown=test_cloud.CloudTests.tearDown
    client=test_cloud.CloudTests.client
    def test_second_sync_transfers_only_changed_record(self):
        a,av=self.client('a');b,bv=self.client('b')
        for i in range(430):av['qso/'+str(i)]={'CALL':'LA1ABC','N':str(i)}
        a.sync();self.assertEqual(b.sync()['downloaded_records'],430)
        self.assertEqual(b.sync()['downloaded_records'],0)
        av['qso/20']['COMMENT']='New report';a.sync()
        self.assertEqual(b.sync()['downloaded_records'],1);self.assertEqual(av,bv)

    def test_pending_conflict_survives_empty_delta_and_restart(self):
        a,av=self.client('a');b,bv=self.client('b')
        av['qso/a']={'CALL':'LA1ABC','COMMENT':'old'};a.sync();b.sync()
        av['qso/a']['COMMENT']='A';bv['qso/a']['COMMENT']='B';a.sync()
        self.assertTrue(b.sync()['conflicts']);self.assertTrue(b.sync()['conflicts'])
        from cloud_sync import Sync
        reopened=Sync(b.folder.parent,lambda:copy.deepcopy(bv),b.apply)
        reopened.config=b.config;reopened.request=b.request
        self.assertTrue(reopened.sync()['conflicts']);reopened.sync({'qso/a':'cloud'})
        self.assertEqual(bv['qso/a']['COMMENT'],'A')

    def test_apply_failure_does_not_advance_cursor(self):
        a,av=self.client('a');b,bv=self.client('b');av['setting/call']='LA1ABC';a.sync();b.sync()
        av['setting/call']='LA2ABC';a.sync();old_apply=b.apply
        def fail(*args):raise OSError('Synthetic disk failure')
        b.apply=fail
        with self.assertRaises(OSError):b.sync()
        b.apply=old_apply;result=b.sync()
        self.assertEqual(result['downloaded_records'],1);self.assertEqual(bv['setting/call'],'LA2ABC')

    def test_restore_republishes_contacts_without_deletion(self):
        a,av=self.client('a');av['qso/a']={'CALL':'LA1ABC'};a.sync();a.sync()
        self.store=server.Store(self.root/'restored.db',registration='open')
        result=a.sync()
        self.assertFalse(result['conflicts']);self.assertEqual(av['qso/a']['CALL'],'LA1ABC')
        self.assertEqual(len(self.store.pull(self.account['user'],0)['items']),1)

    def test_old_server_delta_and_periodic_full_scan(self):
        a,av=self.client('a');b,bv=self.client('b');original=b.request
        def old_server(path,data):
            result=original(path,data)
            return {k:v for k,v in result.items() if k not in ('epoch','high_watermark')}
        b.request=old_server;av['qso/a']={'CALL':'LA1ABC'};a.sync();b.sync()
        self.assertEqual(b.sync()['downloaded_records'],0)
        for path in b.folder.glob('*-remote.json'):
            saved=b.read_private(path);saved['full_at']=0;b.save_private(path,saved)
        self.assertEqual(b.sync()['downloaded_records'],1)

    def test_push_revision_does_not_skip_other_clients_change(self):
        a,av=self.client('a');b,bv=self.client('b');a.sync();b.sync()
        original=a.request
        def race(path,data):
            if path.endswith('/push'):
                self.store.push(self.account['user'],[{'key':'setting/grid','value':'JP53','revision':0}])
            return original(path,data)
        a.request=race;av['setting/call']='LA1ABC';a.sync();a.request=original;a.sync()
        self.assertEqual(av['setting/grid'],'JP53')

if __name__=='__main__':unittest.main()
