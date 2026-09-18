import copy
import json
from pathlib import Path
import socket
import ssl
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from cloud_sync import Sync
from cloud_transport import PUBLIC_CLOUD
from test_accounts import Accounts


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]/'tester')
        self.client = Sync(self.temp.name, lambda: {}, lambda a,b: [])
        self.client.config = {'url':'https://Local-Server:9443', 'certificate':'saved.crt',
            'connect_ip':'192.0.2.10', 'token':'protected-token', 'vault_key':'protected-key',
            'user':'existing-user', 'automatic':True}

    def tearDown(self):
        self.temp.cleanup()

    def test_same_server_keeps_only_connection_fields(self):
        config = self.client.connection_settings({'url':'https://local-server:9443/'})
        self.assertEqual(config, {'url':'https://local-server:9443',
            'certificate':'saved.crt', 'connect_ip':'192.0.2.10'})

    def test_changed_server_never_inherits_certificate_or_ip(self):
        for url in (PUBLIC_CLOUD, 'https://local-server:9444',
                    'https://local-server:9443/cloud', 'https://other-server:9443'):
            with self.subTest(url=url):
                self.assertEqual(self.client.connection_settings({'url':url}),
                    {'url':url,'certificate':''})

    def test_url_path_is_case_sensitive(self):
        self.client.config['url']='https://local-server:9443/Cloud'
        self.assertNotIn('connect_ip', self.client.connection_settings({'url':'https://local-server:9443/cloud'}))

    def test_form_cannot_inject_an_address_hint(self):
        config = self.client.connection_settings({'url':PUBLIC_CLOUD,'connect_ip':'192.0.2.1'})
        self.assertNotIn('connect_ip',config)

    def test_email_actions_reuse_same_connection_without_auth_token(self):
        with patch.object(self.client, 'request', return_value={'ok':True}) as request:
            self.client.email_action('request-reset', {'email':'test@example.test'})
        args = request.call_args.kwargs
        self.assertEqual(args['config']['connect_ip'],'192.0.2.10')
        self.assertNotIn('token',args['config'])
        self.assertFalse(args['authenticated'])

    def test_failed_login_restores_saved_connection_and_never_writes_it(self):
        before = copy.deepcopy(self.client.config)
        with patch.object(self.client,'request',side_effect=ValueError('Simulated login failure')):
            with self.assertRaisesRegex(ValueError,'Simulated'):
                self.client.connect({'url':before['url'],'password':'test password'})
        self.assertEqual(self.client.config,before)
        self.assertFalse((self.client.folder/'connection.json').exists())

    def test_network_errors_are_specific_and_keep_credentials(self):
        self.client.config.update(certificate='',connect_ip='')
        for reason, expected in ((socket.gaierror(-2,'not found'),'Servernavnet'),
            (TimeoutError('Cloud: servernavnet kunne ikke finnes i tide. Kontroller serveradressen.'),'Servernavnet'),
            (TimeoutError('timed out'),'svarte ikke'),
            (ConnectionRefusedError(10061,'refused'),'avviste'),
            (ssl.SSLCertVerificationError(1,'certificate mismatch'),'Sertifikatet')):
            with self.subTest(expected=expected), patch('cloud_sync.exchange',side_effect=urllib.error.URLError(reason)):
                with self.assertRaisesRegex(ValueError,expected):
                    self.client.request('/v1/account/me',{},authenticated=False)
                self.assertEqual(self.client.config['token'],'protected-token')

    def test_logged_out_sync_does_not_claim_automatic_retry(self):
        self.client.config.pop('token')
        with self.assertRaises(ValueError):self.client.sync()
        self.assertEqual(self.client.status['message'],'Logg inn for å synkronisere. Lokale kontakter er beholdt.')


class ReconnectTLS(Accounts):
    def test_relogin_and_connection_check_use_saved_ip_without_dns(self):
        client,_ = self.client('reconnect')
        client.connect({**self.login,'register':True})
        client.disconnect()
        address=f'https://localhost:{self.web.server_port}'
        client.config.update(url=address,connect_ip='127.0.0.1')
        before = client.config['vault_key']
        with patch('cloud_network.socket.getaddrinfo',side_effect=AssertionError('Login used DNS')):
            self.assertEqual(client.check_connection({'url':address})['registration'],'open')
            result=client.connect({**self.login,'url':address})
        self.assertTrue(result['connected'])
        self.assertEqual(client.config['connect_ip'],'127.0.0.1')
        self.assertTrue(client.config['vault_key'])
        saved=json.loads((client.folder/'connection.json').read_text())
        self.assertEqual(saved['connect_ip'],'127.0.0.1')


if __name__=='__main__':unittest.main()
