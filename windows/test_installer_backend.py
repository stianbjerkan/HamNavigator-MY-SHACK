"""Installer regression tests against the real localhost backend HTTP handler.

Only isolated data, an ephemeral port and synthetic audio/Cloud dependencies.
"""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import Mock, patch

import radio_assistant as app

PACKAGING = Path(__file__).resolve().parents[1] / 'packaging'
if not PACKAGING.is_dir():
    PACKAGING = Path(__file__).resolve().parent / 'windows-build/packaging'
spec = importlib.util.spec_from_file_location('installer_preflight', PACKAGING / 'prepare_update.py')
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


@contextmanager
def backend_server(fail_save=False):
    # Never use a real user profile, audio stream, Cloud service or default port.
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        contacts = root / 'contacts.adi'
        contacts.write_bytes(b'SYNTHETIC CONTACTS')
        before = contacts.read_bytes()
        web = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        worker = threading.Thread(target=web.serve_forever, daemon=True)
        lock = threading.Lock()
        lock.acquire()  # A sync already in progress delays the real shutdown.
        cloud = SimpleNamespace(lock=lock, stop=threading.Event(), config={}, status={})
        saved = threading.Event()
        released = False

        def release():
            nonlocal released
            if not released:
                released = True
                lock.release()

        def save():
            if fail_save:
                raise OSError('synthetic disk failure')
            (root / 'saved.txt').write_text('FLUSHED', encoding='ascii')
            saved.set()

        def request_stop():
            req = urllib.request.Request(origin + '/api/backend/stop', b'{}',
                {'Content-Type': 'application/json', 'X-Radio-Token': app.TOKEN})
            with urllib.request.urlopen(req, timeout=3) as response:
                assert json.load(response)['ok']

        origin = f'http://127.0.0.1:{web.server_port}'
        timer = None
        with patch.multiple(app, PORT=web.server_port, DATA_DIR=root, CLOUD=cloud,
                            BACKEND_STOPPING=False, ACTIVE_POSTS=0), \
             patch.object(app, 'refresh_shared'), patch.object(app, 'persist', side_effect=save), \
             patch.object(app, 'set_udp'), patch.object(app.AUDIO, 'stop'), \
             patch.object(app.DX_STOP, 'set'), patch.object(update, 'ORIGIN', origin):
            worker.start()
            def release_later():
                nonlocal timer
                timer = threading.Timer(.4, release)
                timer.start()
            state = SimpleNamespace(root=app.ROOT, pid=os.getpid(), saved=saved,
                request_stop=request_stop, release_later=release_later,
                running=lambda root: {os.getpid()} if worker.is_alive() else set())
            try:
                yield state
            finally:
                release()
                if timer:
                    timer.cancel()
                    timer.join(2)
                web.shutdown()
                web.server_close()
                worker.join(3)
                assert contacts.read_bytes() == before


class InstallerBackendTests(unittest.TestCase):
    def prepare(self, backend, **kwargs):
        return update.prepare(backend.root, timeout=2, running=backend.running,
            close_shell=lambda *args: {backend.pid}, **kwargs)

    def test_already_stopping_backend_is_awaited_without_duplicate_post(self):
        with backend_server() as backend:
            backend.request_stop()
            self.assertTrue(app.BACKEND_STOPPING)
            close = Mock(wraps=update.stop_backend)
            backend.release_later()
            self.prepare(backend, close_backend=close)
            close.assert_not_called()
            self.assertTrue(backend.saved.is_set())

    def test_shutdown_race_503_is_rechecked_and_waited_until_saved(self):
        with backend_server() as backend:
            responses = []
            def race():
                # Shell requests shutdown after preflight's health read.
                backend.request_stop()
                backend.release_later()
                try:
                    update.stop_backend()
                except urllib.error.HTTPError as exc:
                    responses.append(exc.code)
                    raise
            self.prepare(backend, close_backend=race)
            self.assertEqual(responses, [503])
            self.assertTrue(backend.saved.is_set())

    def test_503_without_matching_stopping_state_is_not_ignored(self):
        with backend_server() as backend:
            error = urllib.error.HTTPError(update.ORIGIN, 503, 'unavailable', {}, None)
            with self.assertRaises(urllib.error.HTTPError):
                self.prepare(backend, close_backend=Mock(side_effect=error))
            self.assertFalse(backend.saved.is_set())

    def test_forbidden_shutdown_is_not_ignored(self):
        with backend_server() as backend:
            error = urllib.error.HTTPError(update.ORIGIN, 403, 'forbidden', {}, None)
            with self.assertRaises(urllib.error.HTTPError):
                self.prepare(backend, close_backend=Mock(side_effect=error))
            self.assertFalse(backend.saved.is_set())

    def test_failed_final_save_still_blocks_installation(self):
        with backend_server(fail_save=True) as backend:
            backend.request_stop()
            backend.release_later()
            with self.assertRaises(TimeoutError):
                self.prepare(backend)
            self.assertFalse(backend.saved.is_set())


if __name__ == '__main__':
    unittest.main()
