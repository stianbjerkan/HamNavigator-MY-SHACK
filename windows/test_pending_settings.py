import base64
import copy
import json
import unittest
from unittest.mock import patch

import settings_transfer as transfer
from cloud_sync import Sync
from package_support import prepare_bundle
import test_accounts
from test_settings_merge import CONFIGURED, EMPTY, profile


class PendingSettings(unittest.TestCase):
    setUp = test_accounts.Accounts.setUp
    tearDown = test_accounts.Accounts.tearDown
    client = test_accounts.Accounts.client

    def receiver(self):
        origin, values = self.client('origin')
        digital = {'ms_settings': base64.b64encode(b'remote-settings').decode()}
        values.update({'map/preferences': profile(CONFIGURED), 'digital/preferences': digital})
        origin.connect({**self.login, 'register': True})
        origin.sync()
        root, data = self.root/'receiver/app', self.root/'receiver/data'
        data.mkdir(parents=True)
        state = {'settings': {}, 'qsos': [{'CALL': 'KEEP', 'QSO_DATE': '20260913', 'TIME_ON': '090000'}]}
        (data/'data.json').write_text(json.dumps(state))
        map_dir = transfer.folder('map/preferences', root, data)
        map_dir.mkdir(parents=True)
        local = copy.deepcopy(EMPTY)
        local.update(appLogs=[{'file': 'keep-local.adi'}], trustedQsl={'binaryFile': 'local-tqsl.exe'})
        (map_dir/'app-settings.json').write_text(json.dumps(local))
        def snapshot():
            settings = json.loads((data/'data.json').read_text())['settings']
            return transfer.snapshot(root, data, settings)
        def apply(items, captured):
            for key, value in items.items():
                transfer.stage(key, value, root, data, json.loads((data/'data.json').read_text())['settings'])
            return list(items)
        receiver = Sync(data, snapshot, apply)
        receiver.connect(self.login)
        self.assertEqual(receiver.sync()['conflicts'], [])
        # Digital saves its own runtime settings while the desktop closes.
        digital_dir = transfer.folder('digital/preferences', root, data)
        digital_dir.mkdir(parents=True)
        (digital_dir/'ms_settings').write_bytes(b'local-settings-on-exit')
        return origin, values, receiver, root, data, map_dir, digital_dir, state

    def test_digital_conflict_does_not_block_passwords_and_is_actionable(self):
        a, values, b, root, data, map_dir, digital_dir, state = self.receiver()
        (data/'cloud/settings-error.txt').write_text('Old global settings error')
        prepare_bundle(root, data)
        self.assertFalse((data/'cloud/settings-error.txt').exists())
        saved = json.loads((map_dir/'app-settings.json').read_text())
        self.assertEqual(saved['adifLog'], CONFIGURED['adifLog'])
        self.assertEqual(saved['appLogs'], [{'file': 'keep-local.adi'}])
        self.assertEqual(saved['trustedQsl'], {'binaryFile': 'local-tqsl.exe'})
        self.assertEqual(json.loads((data/'data.json').read_text()), state)
        self.assertEqual((digital_dir/'ms_settings').read_bytes(), b'local-settings-on-exit')
        for _ in range(2):
            status = b.sync()
            self.assertEqual([c['key'] for c in status['conflicts']], ['digital/preferences'])
            self.assertIn('trenger et valg', status['message'])
            self.assertNotIn('fake-club', json.dumps(status))
        a.sync()
        self.assertEqual(base64.b64decode(values['digital/preferences']['ms_settings']), b'remote-settings')
        # An explicit local choice retires the held download only after upload.
        self.assertEqual(b.sync({'digital/preferences': 'local'})['conflicts'], [])
        self.assertEqual(transfer.pending_conflicts(data), [])
        self.assertNotIn('digital/preferences', transfer.read_private(data/'cloud/settings-pending.json') if (data/'cloud/settings-pending.json').exists() else {})
        a.sync()
        self.assertEqual(base64.b64decode(values['digital/preferences']['ms_settings']), b'local-settings-on-exit')

    def test_cloud_choice_retries_only_the_blocked_group(self):
        _, _, b, root, data, map_dir, digital_dir, _ = self.receiver()
        prepare_bundle(root, data)
        saved_map = (map_dir/'app-settings.json').read_bytes()
        self.assertEqual(b.sync({'digital/preferences': 'cloud'})['conflicts'], [])
        self.assertIn('Digital', b.view()['message'])
        prepare_bundle(root, data)
        self.assertEqual((digital_dir/'ms_settings').read_bytes(), b'remote-settings')
        self.assertEqual((map_dir/'app-settings.json').read_bytes(), saved_map)
        self.assertEqual(transfer.pending_conflicts(data), [])
        self.assertEqual(b.sync()['conflicts'], [])

    def test_changed_my_shack_settings_do_not_block_map_or_change_log(self):
        _, _, _, root, data, map_dir, _, state = self.receiver()
        transfer.stage('setting/preferences', {'udp_port': 9000}, root, data, {})
        state['settings']['udp_port'] = 9999
        (data/'data.json').write_text(json.dumps(state))
        result = transfer.apply_pending(root, data)
        self.assertEqual(set(result['blocked']), {'setting/preferences', 'digital/preferences'})
        self.assertIn('map/preferences', result['applied'])
        self.assertEqual(json.loads((data/'data.json').read_text()), state)
        self.assertEqual(json.loads((map_dir/'app-settings.json').read_text())['adifLog'], CONFIGURED['adifLog'])

    def test_write_failure_rolls_back_applied_files_and_retains_pending(self):
        _, _, _, root, data, map_dir, _, _ = self.receiver()
        originals = {p: p.read_bytes() for p in map_dir.iterdir()}
        pending = (data/'cloud/settings-pending.json').read_bytes()
        replace = transfer.os.replace
        def fail_second_file(source, destination):
            if str(destination).endswith('windows.json'):
                raise OSError('simulated disk failure')
            return replace(source, destination)
        with patch.object(transfer.os, 'replace', side_effect=fail_second_file):
            with self.assertRaises(OSError):
                transfer.apply_pending(root, data)
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual((data/'cloud/settings-pending.json').read_bytes(), pending)
        self.assertEqual(list(map_dir.glob('*.cloud-tmp')), [])
        self.assertEqual(len(list((data/'cloud/settings-backups').glob('*.json'))), 1)

    def test_failed_local_choice_keeps_pending_conflict(self):
        _, _, b, root, data, _, _, _ = self.receiver()
        prepare_bundle(root, data)
        request = b.request
        def fail_upload(endpoint, payload=None):
            if endpoint == '/v1/push':
                raise OSError('simulated offline connection')
            return request(endpoint, payload)
        with patch.object(b, 'request', side_effect=fail_upload):
            with self.assertRaises(OSError):
                b.sync({'digital/preferences': 'local'})
        self.assertEqual([c['key'] for c in transfer.pending_conflicts(data)], ['digital/preferences'])
        self.assertEqual([c['key'] for c in b.sync()['conflicts']], ['digital/preferences'])


if __name__ == '__main__':
    unittest.main()
