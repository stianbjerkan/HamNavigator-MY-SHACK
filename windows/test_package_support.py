import json
from pathlib import Path
import tempfile
import unittest
from package_support import prepare_bundle,program_defaults,launch_arguments,configure_shared_map_log,shared_app_logs

class PackageTests(unittest.TestCase):
    def test_shared_map_log_replaces_stale_exports_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root/'Radioassistent'
            profile = root/'HamNavigator-Map/Ginternal/app-settings.json'
            profile.parent.mkdir(parents=True)
            source = root/'radioassistent.adi'; source.write_text('old export kept')
            other = {'file': r'C:\WSJT-X\wsjtx_log.adi', 'enabled': False}
            settings = {'appLogs': [{'file': str(source), 'enabled': True},
                        {'file': r'C:\old\HAMNAVIGATOR.ADI', 'enabled': False}, other],
                        'qrz': {'apiKey': 'synthetic'}, 'startupLogs': ['unrelated.adi']}
            original = json.dumps(settings).encode(); profile.write_bytes(original)
            self.assertTrue(configure_shared_map_log(data))
            current = json.loads(profile.read_text())
            self.assertEqual(current['appLogs'], [{'file': str(data/'log/hamnavigator.adi'), 'enabled': True}, other])
            self.assertEqual(current['qrz'], settings['qrz'])
            self.assertEqual(current['startupLogs'], settings['startupLogs'])
            self.assertEqual(source.read_text(), 'old export kept')
            backups = list(profile.parent.glob('before-shared-log-*.json'))
            self.assertEqual(len(backups), 1); self.assertEqual(backups[0].read_bytes(), original)
            self.assertFalse(configure_shared_map_log(data))
            self.assertEqual(len(list(profile.parent.glob('before-shared-log-*.json'))), 1)

    def test_shared_map_log_seeds_first_run(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)/'custom-profile'
            self.assertTrue(configure_shared_map_log(data))
            profile = data.parent/'HamNavigator-Map/Ginternal/app-settings.json'
            self.assertEqual(json.loads(profile.read_text())['appLogs'][0]['file'], str(data/'log/hamnavigator.adi'))

    def test_corrupt_map_settings_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)/'Radioassistent'
            profile = data.parent/'HamNavigator-Map/Ginternal/app-settings.json'
            profile.parent.mkdir(parents=True); profile.write_bytes(b'broken settings')
            with self.assertRaises(ValueError): configure_shared_map_log(data)
            self.assertEqual(profile.read_bytes(), b'broken settings')

    def test_hamnavigator_log_directory_created_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            digital=root/'release/HamNavigator'
            digital.mkdir(parents=True)
            (root/'BUNDLE.json').write_text('{}')
            (digital/'HamNavigator.exe').write_bytes(b'placeholder')
            prepare_bundle(root,root/'user')
            log=digital/'log/mshvlog.edim'
            log.write_text('existing contacts')
            prepare_bundle(root,root/'user')
            self.assertEqual(log.read_text(),'existing contacts')

    def test_developer_app_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            prepare_bundle(root,root/'user')
            self.assertFalse((root/'user').exists())
            self.assertEqual(program_defaults(root,root/'user'),{})
            self.assertEqual(launch_arguments('gridtracker',root,root/'user'),[])

    def test_clean_first_run_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'package'
            source=root/'programs/MSHV/settings'
            source.mkdir(parents=True)
            (root/'BUNDLE.json').write_text('{}')
            (source/'ms_stinfonet').write_text('udp_broad_port=2237\n')
            (source.parent/'MSHV_WIN64.exe').write_bytes(b'test program placeholder')
            data=Path(directory)/'new user'
            prepare_bundle(root,data)
            paths=program_defaults(root,data)
            self.assertTrue(Path(paths['mshv_path']).is_file())
            gt=data/'GridTracker/Ginternal/app-settings.json'
            config=json.loads(gt.read_text())
            self.assertEqual(config['app']['wsjtUdpPort'],2237)
            self.assertEqual(config['app']['wsjtForwardUdpPort'],2238)
            self.assertNotIn('call',config)
            gt.write_text('{"personal_setting":"keep"}')
            log=data/'programs/MSHV/log'
            log.mkdir()
            (log/'mshvlog.adi').write_text('existing user log')
            prepare_bundle(root,data)
            self.assertEqual(gt.read_text(),'{"personal_setting":"keep"}')
            self.assertEqual((log/'mshvlog.adi').read_text(),'existing user log')
            self.assertEqual(launch_arguments('mshv',root,data),[])
            self.assertIn(str(data/'GridTracker'),launch_arguments('gridtracker',root,data)[0])

if __name__=='__main__':unittest.main()
