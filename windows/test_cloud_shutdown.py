"""Shutdown boundaries use synthetic profiles and never contact a Cloud server."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cloud_sync import Sync


class CloudShutdownTests(unittest.TestCase):
    def test_stop_during_presence_does_not_start_sync_or_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            sync = Sync(Path(folder), lambda: {}, lambda *args: [])
            sync.config['automatic'] = True
            def presence():
                sync.authorized = True
                sync.stop.set()
            sync.presence = presence
            sync.sync = Mock()
            # A real worker should wake immediately, not sleep ten seconds.
            sync.wake.set()
            with patch('log_delivery.Outbox') as outbox:
                sync.start()
                sync.worker.join(2)
                self.assertFalse(sync.worker.is_alive())
                sync.sync.assert_not_called()
                outbox.assert_not_called()

    def test_stop_during_sync_does_not_start_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            sync = Sync(Path(folder), lambda: {}, lambda *args: [])
            sync.config['automatic'] = True
            sync.authorized = True
            sync.presence = lambda: None
            sync.sync = sync.stop.set
            sync.wake.set()
            with patch('log_delivery.Outbox') as outbox:
                sync.start()
                sync.worker.join(2)
                self.assertFalse(sync.worker.is_alive())
                outbox.assert_not_called()

    def test_stopped_sync_never_starts_new_snapshot_or_network(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Mock(return_value={})
            sync = Sync(Path(folder), snapshot, lambda *args: [])
            sync.stop.set()
            with patch.object(sync, '_sync') as run:
                sync.sync()
                run.assert_not_called()
                snapshot.assert_not_called()

    def test_stopped_presence_never_starts_network(self):
        with tempfile.TemporaryDirectory() as folder:
            sync = Sync(Path(folder), lambda: {}, lambda *args: [])
            sync.config['token'] = 'SYNTHETIC'
            sync.stop.set()
            with patch.object(sync, 'request') as request:
                sync.presence()
                request.assert_not_called()

    def test_stopped_outbox_never_reads_or_sends_a_delivery(self):
        from log_delivery import Outbox
        with tempfile.TemporaryDirectory() as folder:
            sync = Sync(Path(folder), lambda: {}, lambda *args: [])
            sync.config['token'] = 'SYNTHETIC'
            sync.authorized = True
            sync.stop.set()
            outbox = Outbox(sync)
            with patch.object(outbox, 'folder') as read, patch.object(outbox, 'send') as send:
                outbox.tick()
                read.assert_not_called()
                send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
