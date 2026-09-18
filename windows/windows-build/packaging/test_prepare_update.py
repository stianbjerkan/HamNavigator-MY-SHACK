import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import prepare_update as update


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        (self.root/'runtime').mkdir()
        (self.root/'runtime/pythonw.exe').touch()
        (self.root/'desktop_host.py').touch()
        self.launch=Mock()
        self.clock=0
    def pause(self,seconds):self.clock+=seconds
    def run_prepare(self,running,**extra):
        return update.prepare(self.root,timeout=1,running=running,launch=self.launch,
            now=lambda:self.clock,pause=self.pause,**extra)
    def test_closed_install_does_not_start_app(self):
        self.run_prepare(lambda root:set())
        self.launch.assert_not_called()
    def test_waits_for_all_processes_and_normal_save(self):
        probe=Mock()
        self.run_prepare(Mock(side_effect=[{1,2},{1,2},{2,3},set()]),inspect_backend=probe)
        self.assertEqual(self.launch.call_args.args[0][-1],'--close')
        self.assertEqual(self.clock,.5)
        probe.assert_not_called()
    def test_refused_close_does_not_allow_install(self):
        stop=Mock()
        with self.assertRaises(TimeoutError):
            self.run_prepare(lambda root:{1,2},inspect_backend=Mock(),close_backend=stop)
        stop.assert_not_called()
    def test_failed_close_command_blocks_install(self):
        self.launch.side_effect=subprocess.TimeoutExpired('close',12)
        with self.assertRaises(subprocess.TimeoutExpired):self.run_prepare(lambda root:{1,2})
    def test_lone_matching_backend_stopped_once_and_waited(self):
        stop=Mock()
        self.run_prepare(Mock(side_effect=[{1},{1},{1},set()]),inspect_backend=lambda *a:1,close_backend=stop)
        stop.assert_called_once_with()
    def test_other_backend_is_never_stopped(self):
        stop=Mock()
        with self.assertRaises(TimeoutError):
            self.run_prepare(lambda root:{1},inspect_backend=lambda *a:None,close_backend=stop)
        stop.assert_not_called()
    def test_backend_health_must_match_pid_root_and_app(self):
        valid={'app':'HamNavigator MY SHACK','pid':1,'root':str(self.root),'can_stop':True}
        def inspect(info):
            with patch.object(update.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(info).encode())):
                return update.backend(self.root,{1})
        self.assertEqual(inspect(valid),1)
        for override in ({'root':str(self.root)+'-other'},{'pid':2},{'app':'other'},{'can_stop':False}):
            self.assertIsNone(inspect({**valid,**override}))

if __name__=='__main__':unittest.main()
