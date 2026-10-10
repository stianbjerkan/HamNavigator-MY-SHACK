"""Offline checks for the complete Windows mode information; no radio/profile access."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODES = ('FT8', 'FT4', 'FT2', 'Q65A', 'Q65B', 'Q65C', 'Q65D',
         'JT65A', 'JT65B', 'JT65C', 'MSK144', 'MSKMS', 'FSK441', 'FSK315',
         'ISCAT-A', 'ISCAT-B', 'JTMS', 'JT6M', 'PI4')


class DigitalInformationTests(unittest.TestCase):
    def pages(self):
        for language in ('nb', 'en', 'sv'):
            path = ROOT / ('app.html' if language == 'nb' else f'languages/{language}/app.html')
            yield language, path.read_text(encoding='utf-8')

    def all_modes(self, text):
        for mode in MODES:
            self.assertRegex(text, r'\b' + re.escape(mode) + r'\b', mode)

    def test_digital_page_lists_every_mode_in_every_language(self):
        for language, page in self.pages():
            with self.subTest(language=language):
                section = page.split('<section id="page-ft8"', 1)[1].split('</section>', 1)[0]
                self.all_modes(section)
                self.assertIn('19', section)

    def test_searchable_chapter_has_modes_and_selection_instructions(self):
        for language, page in self.pages():
            with self.subTest(language=language):
                chapter = page.split('id="manual-digital"', 1)[1].split('</details>', 1)[0]
                self.all_modes(chapter)
                self.assertIn('Windows', chapter)
                self.assertIn('Mode Switcher Buttons', chapter)
                self.assertIn('Mobile', chapter)
                self.assertEqual(page.count('class="manual-chapter card"'), 33)

    def test_all_generated_handbooks_have_current_version(self):
        version = (ROOT / 'VERSION').read_text().strip()
        for path in (ROOT / 'manuals').glob('*.html'):
            with self.subTest(path=path.name):
                self.assertIn(version, path.read_text(encoding='utf-8'))

    def test_digital_and_my_shack_offline_guides_list_modes(self):
        for suffix in ('', '.en', '.sv'):
            for name in ('HamNavigator', 'HamNavigator-Digital', 'HamNavigator-Digital-Qt'):
                with self.subTest(name=name + suffix):
                    text = (ROOT / 'manuals' / (name + suffix + '.html')).read_text(encoding='utf-8')
                    self.all_modes(text)
                    self.assertNotIn('Arbeidsrekkefølge for FT8/FT4', text)
                    self.assertNotIn('FT8/FT4 workflow', text)
                    self.assertNotIn('Arbetsgång för FT8/FT4', text)
                    if name.endswith('-Qt'):
                        self.assertNotIn('<script', text)
                        self.assertIn('<a name="digital"></a>', text)

    def test_fixed_catalogs_match_visible_copy(self):
        source = dict(self.pages())
        for language in ('en', 'sv'):
            catalog = json.loads((ROOT / f'languages/{language}.json').read_text(encoding='utf-8'))
            descriptions = [(key, value) for key, value in catalog.items() if key.startswith('19 digitale modi:')]
            self.assertEqual(len(descriptions), 1)
            key, value = descriptions[0]
            self.assertIn(key, source['nb'])
            self.assertIn(value, source[language])
            self.all_modes(value)

    def test_protocol_identifiers_and_logging_mode_values_are_unchanged(self):
        import shared_log
        self.assertTrue(set(MODES).issubset(set(shared_log.MODES.values())))
        for _, page in self.pages():
            self.assertIn('id="page-ft8"', page)
            self.assertIn('id="udp-start"', page)
            self.assertIn('<option>FT8</option>', page)


if __name__ == '__main__':
    unittest.main()
