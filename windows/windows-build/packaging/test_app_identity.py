from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from app_identity import PRODUCTS, SERVER, editor, pe_sections, verify_file


class WindowsIdentityTests(unittest.TestCase):
    def test_all_shipped_entrypoints_have_the_correct_windows_identity(self):
        for relative, product in PRODUCTS.items():
            with self.subTest(product=product):
                verify_file(SERVER / 'bygg/klient' / relative, product, (SERVER / 'Kildekode/klient/VERSION').read_text().strip())

    def test_guard_rejects_a_renamed_executable_with_old_embedded_brand(self):
        with tempfile.TemporaryDirectory(dir=SERVER / 'tester', prefix='identity-') as temp:
            path = Path(temp) / 'HamNavigatorMap.exe'
            shutil.copy2(SERVER / 'bygg/klient/Radioassistent.exe', path)
            verify_file(path, 'HamNavigator MY SHACK', (SERVER / 'Kildekode/klient/VERSION').read_text().strip())
            code_before = pe_sections(path)
            subprocess.run([str(editor()), str(path), '--set-version-string', 'FileDescription', 'GridTracker2'], check=True)
            self.assertEqual(code_before, pe_sections(path))
            with self.assertRaises(AssertionError):
                verify_file(path, 'HamNavigator MY SHACK', (SERVER / 'Kildekode/klient/VERSION').read_text().strip())

    def test_map_metadata_and_original_notices_are_both_present(self):
        app = SERVER / 'bygg/klient/release/HamNavigator-Map/resources/app'
        package = json.loads((app / 'package.json').read_text(encoding='utf-8'))
        for name in ('productName', 'description', 'author', 'homepage'):
            self.assertNotRegex(package[name].lower(), 'gridtracker|mshv')
        self.assertEqual(package['hamnavigatorVersion'], (SERVER / 'Kildekode/klient/VERSION').read_text().strip())
        self.assertIn('GridTracker', (app / 'OPPHAV.txt').read_text(encoding='utf-8'))
        self.assertIn('MSHV', (SERVER / 'bygg/klient/release/HamNavigator/OPPHAV.txt').read_text(encoding='utf-8'))
        text = (app / 'src/main/index.js').read_text(encoding='utf-8')
        self.assertNotIn('GridTracker2 starting up!', text)
        self.assertIn("app.setName('HamNavigator Map')", text)


if __name__ == '__main__':
    unittest.main()
