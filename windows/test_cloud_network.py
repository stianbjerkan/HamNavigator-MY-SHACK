import copy
import ssl
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import cloud_network as network
from test_cloud import CloudTests, server
from test_accounts import Accounts


class NetworkTests(unittest.TestCase):
    def tearDown(self):
        with network._lock: network._lookups.clear()

    def test_hung_dns_times_out_and_reuses_one_worker(self):
        release=threading.Event();calls=[]
        def stuck(*args):
            calls.append(args);release.wait(2);return []
        try:
            with patch.object(network.socket,'getaddrinfo',side_effect=stuck),patch.object(network,'DNS_TIMEOUT',.03):
                before=time.monotonic()
                for _ in range(3):
                    with self.assertRaises(TimeoutError):network.resolve('hung.invalid',9443,20)
                self.assertLess(time.monotonic()-before,.5)
                self.assertEqual(len(calls),1)
        finally:release.set()

    def test_numeric_address_does_not_use_dns(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
        try:
            with patch.object(network.socket,'getaddrinfo',side_effect=AssertionError('DNS used')):
                client=network.connect(listener.getsockname(),1);client.close()
        finally:listener.close()


class TLSChecks(Accounts):
    def test_address_hint_retains_certificate_hostname_validation(self):
        context=ssl.create_default_context(cafile=str(self.root/'server.crt'))
        handler=network.HTTPSHandler(context,'LOCALHOST','127.0.0.1')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),handler)
        with opener.open(f'https://localhost:{self.web.server_port}/health',timeout=2) as r:
            self.assertEqual(r.status,200)
        bad=urllib.request.build_opener(urllib.request.ProxyHandler({}),network.HTTPSHandler(context,'wrong.invalid','127.0.0.1'))
        with self.assertRaises(urllib.error.URLError):bad.open(f'https://wrong.invalid:{self.web.server_port}/health',timeout=2)


class SchedulerChecks(CloudTests):
    def test_auto_starts_without_initial_timer_delay(self):
        a,_=self.client('immediate');finished=threading.Event()
        a.config['automatic']=True
        a.presence=lambda:setattr(a,'authorized',True)
        a.sync=lambda:finished.set()
        a.start()
        try:self.assertTrue(finished.wait(1));self.assertTrue(a.worker.is_alive())
        finally:a.stop.set();a.wake.set();a.worker.join(1)

    def test_repeated_page_fails_without_applying_or_losing_contacts(self):
        a,values=self.client('repeated');values['qso/a']={'CALL':'LA1ABC'}
        before=copy.deepcopy(values)
        a.request=lambda path,data:{'items':[],'more':True}
        with self.assertRaisesRegex(ValueError,'samme loggside'):a.sync()
        self.assertEqual(values,before);self.assertFalse(a.view()['syncing'])
        self.assertIn('Synkronisering stoppet',a.view()['message'])

    def test_unchanged_sync_keeps_dated_backups(self):
        a,values=self.client('backup');values['qso/a']={'CALL':'LA1ABC'}
        a.sync();first=list((a.folder/'backups').rglob('*.json'))
        a.sync();self.assertEqual(list((a.folder/'backups').rglob('*.json')),first)
        values['qso/b']={'CALL':'LA2ABC'};a.sync()
        self.assertEqual(len(list((a.folder/'backups').rglob('*.json'))),2)


if __name__=='__main__':unittest.main()
