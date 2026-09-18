import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import radio_assistant as app


class BackendLifecycleTests(unittest.TestCase):
    def test_installer_start_uses_backend_then_no_radio_resume(self):
        import sys
        with patch.object(sys,'argv',['radio_assistant.py','--no-resume']), \
             patch.object(app,'healthy',return_value=True), \
             patch.object(app,'open_desktop',return_value=True) as desktop, \
             patch.object(app,'open_app') as regular:
            app.main()
            desktop.assert_called_once_with(resume=False)
            regular.assert_not_called()

    def test_no_resume_is_forwarded_to_desktop_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'runtime').mkdir();(root/'runtime/pythonw.exe').touch()
            with patch.multiple(app,ROOT=root,DATA_DIR=root/'data'),patch.object(app.subprocess,'Popen') as launch:
                self.assertTrue(app.open_desktop(resume=False))
                self.assertEqual(launch.call_args.args[0][-1],'--no-resume')

    def test_audio_driver_crash_returns_error_while_health_stays_available(self):
        import concurrent.futures,subprocess
        from types import SimpleNamespace
        import callsign_audio as audio
        web=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=web.serve_forever,daemon=True)
        audio.DEVICE_CACHE=None;audio.DEVICE_CACHE_UNTIL=0
        with patch.object(app,'PORT',web.server_port),patch.object(app,'CLOUD',SimpleNamespace(authorized=True)),patch.object(audio.subprocess,'run',return_value=subprocess.CompletedProcess([],0xC0000005,b'',b'')):
            worker.start()
            url=f'http://127.0.0.1:{web.server_port}'
            try:
                req=urllib.request.Request(url+'/api/audio/devices',b'{}',headers={'Content-Type':'application/json','X-Radio-Token':app.TOKEN})
                with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req,timeout=3)
                self.assertEqual(caught.exception.code,400)
                self.assertIn('Cloud kjører fortsatt',json.load(caught.exception)['error'])
                with urllib.request.urlopen(url+'/api/health',timeout=3) as response:
                    self.assertEqual(json.load(response)['app'],'HamNavigator MY SHACK')
            finally:web.shutdown();web.server_close();worker.join(3)

    def test_login_gate_preserves_data_and_rejects_program_launch(self):
        import io
        from types import SimpleNamespace
        handler=object.__new__(app.Handler);handler.valid_host=lambda:True
        replies=[];handler.send=lambda value,status=200,**kwargs:replies.append((status,value))
        with patch.object(app,'CLOUD',SimpleNamespace(authorized=False)),patch.object(app,'open_desktop') as launch:
            handler.path='/api/state';handler.do_GET()
            self.assertTrue(replies[-1][1]['login_required']);self.assertEqual(replies[-1][1]['qsos'],[])
            handler.path='/api/export';handler.do_GET();self.assertEqual(replies[-1][0],401)
            handler.path='/api/desktop/open';handler.headers={'X-Radio-Token':app.TOKEN,'Content-Length':'2'};handler.rfile=io.BytesIO(b'{}')
            handler.handle_post();self.assertEqual(replies[-1][0],401);launch.assert_not_called()

    def test_health_rejects_old_version_or_installation(self):
        good={'app':'HamNavigator MY SHACK','version':app.RUNNING_VERSION,'root':str(app.ROOT)}
        with patch.object(app,'backend_info',return_value=good):self.assertTrue(app.healthy())
        for different in ({'version':'1.8.0'},{'root':'C:/old-install'},{'stopping':True}):
            with patch.object(app,'backend_info',return_value={**good,**different}):self.assertFalse(app.healthy())

    def test_authenticated_shutdown_flushes_before_port_is_released(self):
        folder=Path(__file__).parents[2]/'tester';folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            web=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            saved=threading.Event()
            with patch.multiple(app,PORT=web.server_port,DATA_DIR=Path(temp),CLOUD=None,BACKEND_STOPPING=False,ACTIVE_POSTS=0), \
                 patch.object(app,'refresh_shared'),patch.object(app,'persist',side_effect=saved.set), \
                 patch.object(app,'set_udp'),patch.object(app.AUDIO,'stop'),patch.object(app.DX_STOP,'set'):
                worker=threading.Thread(target=web.serve_forever,daemon=True);worker.start()
                url=f'http://127.0.0.1:{web.server_port}'
                try:
                    with urllib.request.urlopen(url+'/api/health') as response:health=json.load(response)
                    self.assertTrue(health['can_stop']);self.assertEqual(health['version'],app.RUNNING_VERSION)
                    req=urllib.request.Request(url+'/api/backend/stop',b'{}',headers={'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
                    self.assertEqual(err.exception.code,403);self.assertFalse(saved.is_set())
                    req.add_header('X-Radio-Token',app.TOKEN)
                    with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['ok'])
                    worker.join(5);self.assertFalse(worker.is_alive());self.assertTrue(saved.is_set())
                finally:
                    web.shutdown();web.server_close();worker.join(5)

    def test_failed_save_keeps_backend_available(self):
        folder=Path(__file__).parents[2]/'tester'
        with tempfile.TemporaryDirectory(dir=folder) as temp, \
             patch.multiple(app,DATA_DIR=Path(temp),CLOUD=None,BACKEND_STOPPING=True,ACTIVE_POSTS=0), \
             patch.object(app,'refresh_shared'),patch.object(app,'persist',side_effect=OSError('disk full')), \
             patch.object(app,'set_udp'),patch.object(app.AUDIO,'stop'),patch.object(app.DX_STOP,'set'):
            from unittest.mock import Mock
            server=Mock();app.stop_backend(server)
            server.shutdown.assert_not_called();self.assertFalse(app.BACKEND_STOPPING)
            self.assertIn('disk full',(Path(temp)/'startup.log').read_text())


if __name__=='__main__':unittest.main()
