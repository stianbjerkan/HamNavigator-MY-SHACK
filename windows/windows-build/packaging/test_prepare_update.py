import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, MagicMock, patch
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
        extra.setdefault('close_shell', Mock(return_value=set()))
        return update.prepare(self.root,timeout=1,backend_timeout=1,running=running,launch=self.launch,
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
    def test_direct_shell_close_does_not_start_installed_qt_again(self):
        close = Mock(return_value={1})
        self.run_prepare(Mock(side_effect=[{1,2},{1,2},set()]),close_shell=close)
        close.assert_called_once_with(self.root,{1,2})
        self.launch.assert_not_called()
    def test_direct_close_still_waits_for_refused_save(self):
        with self.assertRaises(TimeoutError):
            self.run_prepare(lambda root:{1,2},close_shell=lambda *a:{1})
        self.launch.assert_not_called()
    def test_pipe_error_blocks_instead_of_bypassing_shutdown(self):
        with self.assertRaises(OSError):
            self.run_prepare(lambda root:{1,2},close_shell=Mock(side_effect=OSError('pipe failed')))
        self.launch.assert_not_called()
    def test_lone_matching_backend_stopped_once_and_waited(self):
        stop=Mock()
        self.run_prepare(Mock(side_effect=[{1},{1},{1},set()]),inspect_backend=lambda *a:{'pid':1,'stopping':False},close_backend=stop)
        stop.assert_called_once_with()
        self.launch.assert_not_called()
    def test_stopping_backend_is_only_waited_for(self):
        stop=Mock()
        self.run_prepare(Mock(side_effect=[{1},{1},{1},set()]),
            inspect_backend=lambda *a:{'pid':1,'stopping':True},close_backend=stop)
        stop.assert_not_called()
    def test_verified_stopping_backend_can_finish_after_gui_timeout(self):
        stop=Mock()
        update.prepare(self.root,timeout=1,backend_timeout=3,
            running=lambda root:{1} if self.clock<2 else set(),
            inspect_backend=lambda *a:{'pid':1,'stopping':True},
            close_shell=lambda *a:set(),close_backend=stop,launch=self.launch,
            now=lambda:self.clock,pause=self.pause)
        self.assertEqual(self.clock,2)
        stop.assert_not_called()
        self.launch.assert_not_called()

    def test_verified_backend_still_has_finite_deadline(self):
        with self.assertRaises(TimeoutError):
            update.prepare(self.root,timeout=1,backend_timeout=3,
                running=lambda root:{1},inspect_backend=lambda *a:{'pid':1,'stopping':True},
                close_shell=lambda *a:set(),launch=self.launch,
                now=lambda:self.clock,pause=self.pause)
        self.assertEqual(self.clock,3)
    def test_failed_save_after_stopping_does_not_extend_or_retry(self):
        stop=Mock()
        with self.assertRaises(RuntimeError):
            update.prepare(self.root,timeout=1,backend_timeout=300,
                running=lambda root:{1},
                inspect_backend=lambda *a:{'pid':1,'stopping':self.clock<.5},
                close_shell=lambda *a:set(),close_backend=stop,
                now=lambda:self.clock,pause=self.pause)
        self.assertEqual(self.clock,1)
        stop.assert_not_called()

    def test_another_process_does_not_inherit_backend_grace_period(self):
        with self.assertRaises(TimeoutError):
            update.prepare(self.root,timeout=1,backend_timeout=300,
                running=lambda root:{1} if self.clock<.5 else {2},
                inspect_backend=lambda root,pids:{'pid':1,'stopping':True} if pids=={1} else None,
                close_shell=lambda *a:set(),now=lambda:self.clock,pause=self.pause)
        self.assertEqual(self.clock,1)
    def test_shutdown_503_after_process_exit_is_safe(self):
        error=urllib.error.HTTPError(update.ORIGIN,503,'unavailable',{},None)
        self.run_prepare(Mock(side_effect=[{1},{1},set(),set()]),
            inspect_backend=lambda *a:{'pid':1,'stopping':False},
            close_backend=Mock(side_effect=error))
    def test_connection_closed_after_process_exit_is_safe(self):
        self.run_prepare(Mock(side_effect=[{1},{1},set(),set()]),
            inspect_backend=lambda *a:{'pid':1,'stopping':False},
            close_backend=Mock(side_effect=urllib.error.URLError('connection closed')))
    def test_shutdown_503_with_different_process_still_blocks(self):
        error=urllib.error.HTTPError(update.ORIGIN,503,'unavailable',{},None)
        with self.assertRaises(urllib.error.HTTPError):
            self.run_prepare(Mock(side_effect=[{1},{1},{2}]),
                inspect_backend=lambda *a:{'pid':1,'stopping':False},
                close_backend=Mock(side_effect=error))
    def test_connection_error_while_not_stopping_still_blocks(self):
        with self.assertRaises(urllib.error.URLError):
            self.run_prepare(lambda *a:{1},
                inspect_backend=lambda *a:{'pid':1,'stopping':False},
                close_backend=Mock(side_effect=urllib.error.URLError('connection failed')))
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
        self.assertEqual(inspect(valid),valid)
        for override in ({'root':str(self.root)+'-other'},{'pid':2},{'app':'other'},{'can_stop':False}):
            self.assertIsNone(inspect({**valid,**override}))

    def test_cli_diagnostics_do_not_leak_exception_details(self):
        log = self.root / 'diagnostics.log'
        error = subprocess.CalledProcessError(73, ['private-command', 'private-token'])
        with patch.object(update, 'prepare', side_effect=error):
            self.assertEqual(update.main([str(self.root), str(log)]), 3)
        entry = json.loads(log.read_text())
        self.assertEqual(entry['child_exit'], 73)
        self.assertEqual(entry['error_type'], 'CalledProcessError')
        self.assertNotIn('private', log.read_text())

    def test_cli_distinguishes_timeout_from_failed_command(self):
        log = self.root / 'timeout.log'
        with patch.object(update, 'prepare', side_effect=TimeoutError('unsaved')):
            self.assertEqual(update.main([str(self.root), str(log)]), 2)
        self.assertEqual(json.loads(log.read_text())['error_type'], 'TimeoutError')

    def test_cli_records_http_status_without_private_response_body(self):
        log = self.root / 'http.log'
        error = urllib.error.HTTPError('http://private-address', 403, 'private-reason',
                                      {}, io.BytesIO(b'private-token'))
        with patch.object(update, 'prepare', side_effect=error):
            self.assertEqual(update.main([str(self.root), str(log)]), 3)
        self.assertEqual(json.loads(log.read_text())['http_status'], 403)
        self.assertNotIn('private', log.read_text())


class PipeIdentityTests(unittest.TestCase):
    def attempt(self, pending, current, written=5):
        kernel = Mock()
        def peer(handle, pid):
            pid._obj.value = 71
            return True
        kernel.GetNamedPipeServerProcessId.side_effect = peer
        kernel.SetNamedPipeHandleState.return_value = True
        pipe = MagicMock()
        pipe.__enter__.return_value = pipe
        pipe.write.return_value = written
        with patch.object(update.ctypes, 'WinDLL', return_value=kernel), \
             patch.object(update.os, 'listdir', return_value=['Radioassistent-' + 'a' * 20, 'other-pipe']), \
             patch.object(update.msvcrt, 'get_osfhandle', return_value=42), \
             patch('builtins.open', return_value=pipe) as opened:
            result = update.request_shell_close(Path('C:/test'), pending, running=lambda root:current)
        self.assertEqual(opened.call_count, 1)
        return result, pipe

    def test_only_verified_pid_gets_a_close_command(self):
        result, pipe = self.attempt({71}, {71})
        self.assertEqual(result, {71})
        pipe.write.assert_called_once_with(b'close')

    def test_other_installation_is_never_closed(self):
        result, pipe = self.attempt({72}, {72})
        self.assertFalse(result)
        pipe.write.assert_not_called()

    def test_stale_pid_is_rechecked_before_close(self):
        result, pipe = self.attempt({71}, set())
        self.assertFalse(result)
        pipe.write.assert_not_called()

    def test_incomplete_command_fails_closed(self):
        with self.assertRaises(OSError):
            self.attempt({71}, {71}, written=3)

if __name__=='__main__':unittest.main()
