import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from update_dialog import UpdateDialog


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, dialog):
        end = time.monotonic() + 5
        while dialog.busy() and time.monotonic() < end:
            QTest.qWait(10)
        self.assertFalse(dialog.busy())

    def test_current_and_network_error_can_retry(self):
        with patch('update_dialog.check_update', side_effect=[OSError('Frakoblet'), None]):
            dialog = UpdateDialog(Path(__file__).parent, None)
            self.wait(dialog)
            self.assertIn('Frakoblet', dialog.status.text())
            dialog.action.click()
            self.wait(dialog)
            self.assertIn('nyeste versjon', dialog.status.text())
            dialog.close()

    def test_click_downloads_and_starts_correct_installer_once(self):
        info = {'version': '1.5.0', 'size': 1200000}
        path = Path('C:/test updates/HamNavigator-MY-SHACK-Setup.exe')
        with patch('update_dialog.check_update', return_value=info), \
             patch('update_dialog.download_update', return_value=path) as download, \
             patch('update_dialog.subprocess.Popen') as launch:
            dialog = UpdateDialog(Path(__file__).parent, None)
            self.wait(dialog)
            self.assertEqual(dialog.action.text(), 'Oppdater nå')
            dialog.action.click()
            dialog.action.click()
            self.wait(dialog)
            self.assertEqual(download.call_count, 1)
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(launch.call_args.args[0][0], str(path))
            self.assertFalse(dialog.action.isEnabled())
            self.assertIn('kontrollert', dialog.status.text())
            dialog.close()

    def test_cancel_waits_for_worker_and_never_launches(self):
        def downloading(info, cache, progress, cancel):
            cancel.wait(3)
            return Path('should-never-start.exe')
        with patch('update_dialog.check_update', return_value={'version': '1.5.0', 'size': 123}), \
             patch('update_dialog.download_update', side_effect=downloading), \
             patch('update_dialog.subprocess.Popen') as launch:
            dialog = UpdateDialog(Path(__file__).parent, None)
            self.wait(dialog)
            dialog.action.click()
            dialog.reject()
            self.wait(dialog)
            launch.assert_not_called()
            self.assertIn('avbrutt', dialog.status.text())
            dialog.close()


if __name__ == '__main__':
    unittest.main()
