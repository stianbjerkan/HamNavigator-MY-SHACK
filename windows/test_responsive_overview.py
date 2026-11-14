import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from cloud_sync import Sync
import radio_assistant as radio


class ResponsiveOverviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.client = Sync(folder.name, None, None)
        self.client.config.update(url='https://example.test', email='a@example.test', token='test-token')
        self.client.authorized = True
        self.query = {'account':['https://example.test','a@example.test'], 'share':True, 'callsign':'LA1QA'}

    def test_directory_works_while_log_sync_holds_its_lock(self):
        result = {'online_directory':{'own_call':'LA1QA','callsigns':['LA1QA']}}
        with patch.object(self.client, 'request', return_value=result), ThreadPoolExecutor(1) as worker:
            with self.client.lock:
                response = worker.submit(self.client.online_directory, self.query, 'LA1QA').result(timeout=2)
        self.assertEqual(response['own_call'], 'LA1QA')

    def test_late_directory_reply_does_not_cross_sessions(self):
        started = threading.Event()
        finish = threading.Event()
        def request(*args, **kwargs):
            started.set()
            self.assertTrue(finish.wait(3))
            return {'online_directory':{'own_call':'LA1QA'}}
        with patch.object(self.client,'request',side_effect=request), ThreadPoolExecutor(1) as worker:
            response = worker.submit(self.client.online_directory,self.query,'LA1QA')
            self.assertTrue(started.wait(2))
            with self.client.account_lock:
                self.client.config['token'] = 'different-test-token'
            finish.set()
            with self.assertRaises(ValueError):
                response.result(timeout=2)

    def test_menu_status_is_independent_of_private_sync_history(self):
        self.client.status.update(deliveries=['x'*1000]*2000, conflicts=['private'])
        summary = self.client.account_status()
        self.assertEqual(set(summary), {'url','email','authorized','admin','connected'})
        self.assertLess(len(json.dumps(summary)), 200)

    def test_empty_merge_skips_reloading_the_station(self):
        with patch.object(radio,'cloud_snapshot') as snapshot, patch.object(radio,'persist') as persist:
            self.assertEqual(radio.cloud_apply({},{}),[])
            snapshot.assert_not_called()
            persist.assert_not_called()
