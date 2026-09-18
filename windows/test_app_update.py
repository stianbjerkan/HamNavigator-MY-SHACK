import copy
import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import app_update as updater


class Response(io.BytesIO):
    def geturl(self):
        return 'https://release-assets.githubusercontent.com/example'


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.data = b'MZ-example-installer'
        self.payload = {'tag_name': 'v1.10.0', 'draft': False, 'prerelease': False,
                        'assets': [{'name': updater.ASSET_NAME, 'size': len(self.data),
                                    'digest': 'sha256:' + hashlib.sha256(self.data).hexdigest(),
                                    'browser_download_url': f'https://github.com/{updater.REPOSITORY}/releases/download/v1.10.0/{updater.ASSET_NAME}'}]}

    def test_semantic_versions_and_no_downgrade(self):
        self.assertEqual(updater.release_info(self.payload, '1.9.0')['version'], '1.10.0')
        self.assertIsNone(updater.release_info(self.payload, '1.10.0'))
        self.assertIsNone(updater.release_info(self.payload, '2.0.0'))
        for field in ['draft', 'prerelease']:
            value = dict(self.payload, **{field: True})
            self.assertIsNone(updater.release_info(value, '1.0.0'))

    def test_invalid_release_fails_closed(self):
        for field, value in [('digest', None), ('digest', 'sha256:abc'),
                             ('browser_download_url', 'https://example.com/malware.exe'),
                             ('size', -1), ('size', True)]:
            payload = copy.deepcopy(self.payload)
            payload['assets'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                updater.release_info(payload, '1.0.0')
        for tag in ['v1.11.0-beta', '../1.2.0', 'unknown']:
            with self.assertRaises(ValueError):
                updater.version_tuple(tag)

    def test_verified_download_and_atomic_destination(self):
        info = updater.release_info(self.payload, '1.0.0')
        progress = []
        with tempfile.TemporaryDirectory() as folder:
            result = updater.download_update(info, folder, lambda *v: progress.append(v),
                                             threading.Event(), lambda *a, **kw: Response(self.data))
            self.assertEqual(result.read_bytes(), self.data)
            self.assertEqual(progress[-1], (len(self.data), len(self.data)))
            self.assertFalse(list(Path(folder).rglob('*.part')))

    def test_corruption_truncation_and_cancel_do_not_install(self):
        info = updater.release_info(self.payload, '1.0.0')
        for data, cancelled in [(b'bad', False), (b'X' * len(self.data), False),
                                (self.data + b'extra', False), (self.data, True)]:
            with tempfile.TemporaryDirectory() as folder:
                cancel = threading.Event()
                if cancelled:
                    cancel.set()
                with self.assertRaises((ValueError, updater.UpdateCancelled)):
                    updater.download_update(info, folder, lambda *a: None, cancel,
                                            lambda *a, **kw: Response(data))
                self.assertFalse(list(Path(folder).rglob('*.exe')))
                self.assertFalse(list(Path(folder).rglob('*.part')))

    def test_install_destination_only_for_packaged_app(self):
        with tempfile.TemporaryDirectory(prefix='HamNavigator with spaces ') as folder:
            self.assertFalse(any(a.startswith('/DIR=') for a in updater.installer_arguments(folder)))
            (Path(folder) / 'BUNDLE.json').write_text('{}')
            (Path(folder) / 'Radioassistent.exe').touch()
            self.assertIn('/DIR=' + str(Path(folder).resolve()), updater.installer_arguments(folder))


if __name__ == '__main__':
    unittest.main()
