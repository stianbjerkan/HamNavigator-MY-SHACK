import concurrent.futures,json,subprocess,threading,time,unittest
from unittest.mock import patch
import callsign_audio as audio

DEVICES=[{'id':1,'name':'Synthetic input','loopback':False,'rate':48000,'channels':1}]

class DeviceScanTests(unittest.TestCase):
    def setUp(self):
        audio.DEVICE_CACHE=None;audio.DEVICE_CACHE_UNTIL=0

    def test_concurrent_webviews_share_scan_without_native_initialization(self):
        gate=threading.Barrier(8)
        def scan(*args,**kwargs):
            time.sleep(.03)
            return subprocess.CompletedProcess(args[0],0,json.dumps(DEVICES).encode(),b'')
        def query(_):gate.wait();return audio.list_devices()
        with patch.object(audio,'load_dependencies',side_effect=AssertionError('Native audio in backend')),patch.object(audio.subprocess,'run',side_effect=scan) as run:
            with concurrent.futures.ThreadPoolExecutor(8) as pool:results=list(pool.map(query,range(8)))
        self.assertEqual(run.call_count,1)
        self.assertTrue(all(result==DEVICES for result in results))
        results[0][0]['name']='changed'
        self.assertEqual(audio.DEVICE_CACHE,DEVICES)

    def test_native_scanner_crash_is_recoverable(self):
        with patch.object(audio.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0xC0000005,b'',b'crash'),subprocess.CompletedProcess([],0,json.dumps(DEVICES).encode(),b'')]):
            with self.assertRaisesRegex(ValueError,'Cloud kjører fortsatt'):audio.list_devices()
            self.assertEqual(audio.list_devices(),DEVICES)

    def test_timeout_and_invalid_output_do_not_poison_retry(self):
        for result in (subprocess.TimeoutExpired('scan',12),subprocess.CompletedProcess([],0,b'bad-json',b''),subprocess.CompletedProcess([],0,b'[{}]',b'')):
            with self.subTest(result=type(result).__name__),patch.object(audio.subprocess,'run',side_effect=result if isinstance(result,Exception) else None,return_value=result):
                with self.assertRaises(ValueError):audio.list_devices()
                self.assertIsNone(audio.DEVICE_CACHE)

if __name__=='__main__':unittest.main()
