"""Exercise real export HTTP responses with an isolated synthetic log."""
import copy
import threading
import unittest
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import radio_assistant as app


class ExportDownloadTests(unittest.TestCase):
    def test_filenames_and_contacts_through_http(self):
        state = copy.deepcopy(app.DEFAULTS)
        contact = {'CALL': 'LA1ABC', 'QSO_DATE': '20260918', 'TIME_ON': '080000',
                   'MODE': 'SSB', 'BAND': '20m', 'FREQ': '14.250'}
        state['qsos'] = [contact]
        with ThreadingHTTPServer(('127.0.0.1', 0), app.Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            with patch.object(app, 'PORT', server.server_port), \
                 patch.object(app, 'STATE', state), patch.object(app, 'SHARED', None), \
                 patch.object(app, 'CLOUD', SimpleNamespace(authorized=True)):
                thread.start()
                try:
                    for query, name in [('', 'hamnavigator.adi'), ('?program=', 'hamnavigator.adi'),
                                        ('?program=pota', 'pota.adi'), ('?program=sota', 'sota.adi')]:
                        with self.subTest(query=query), urllib.request.urlopen(
                                f'http://127.0.0.1:{server.server_port}/api/export{query}', timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.headers['Content-Disposition'], f'attachment; filename="{name}"')
                            rows = app.parse_adif(response.read().decode('ascii'))
                            if not query or query == '?program=':
                                self.assertEqual(len(rows), 1)
                                self.assertEqual(rows[0]['CALL'], contact['CALL'])
                            else:
                                self.assertEqual(rows, [])
                    self.assertEqual(state['qsos'], [contact])
                finally:
                    server.shutdown()
                    thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
