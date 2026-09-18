"""Bound DNS as well as TCP timeouts, without weakening TLS hostname checks."""
import ui_language
import functools
import http.client
import ipaddress
import socket
import threading
import time
import urllib.request

DNS_TIMEOUT = 5
_lock = threading.Lock()
_lookups = {}


def resolve(host, port, timeout):
    key = (host, port)
    with _lock:
        lookup = _lookups.get(key)
        if lookup and lookup['done'].is_set() and time.monotonic() - lookup['at'] > 60:
            _lookups.pop(key)
            lookup = None
        if lookup is None:
            # An unresponsive Windows DNS call cannot be cancelled. Keep one
            # daemon per destination, and cap these instead of leaking threads.
            for old in list(_lookups):
                if _lookups[old]['done'].is_set() and time.monotonic()-_lookups[old]['at'] > 60:
                    _lookups.pop(old)
            if len(_lookups) >= 16:
                raise TimeoutError(ui_language.t('Cloud: adresseoppslag er opptatt. Prøver igjen.'))
            lookup = {'done': threading.Event(), 'at': time.monotonic()}
            _lookups[key] = lookup
            def work():
                try: lookup['addresses'] = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
                except OSError as error: lookup['error'] = error
                finally:
                    lookup['at'] = time.monotonic()
                    lookup['done'].set()
            threading.Thread(target=work, daemon=True, name='HamNavigatorDNS').start()
    if not lookup['done'].wait(min(DNS_TIMEOUT, timeout)):
        raise TimeoutError(ui_language.t('Cloud: servernavnet kunne ikke finnes i tide. Kontroller serveradressen.'))
    if 'error' in lookup: raise lookup['error']
    return lookup['addresses']


def connect(address, timeout=20, source_address=None, *, override=None, **unused):
    timeout = 20 if timeout is None or timeout is socket._GLOBAL_DEFAULT_TIMEOUT else timeout
    deadline = time.monotonic() + timeout
    host, port = address
    target = override or host
    try:
        ip = ipaddress.ip_address(target)
        af = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
        addresses = [(af, socket.SOCK_STREAM, 0, '', (str(ip), port))]
    except ValueError:
        addresses = resolve(target, port, timeout)
    error = OSError(ui_language.t('Cloud-serveren har ingen nettverksadresse.'))
    for af, kind, proto, _, destination in addresses:
        remaining = deadline-time.monotonic()
        if remaining <= 0: raise TimeoutError(ui_language.t('Cloud: tilkoblingen tok for lang tid.'))
        connection = socket.socket(af, kind, proto)
        try:
            connection.settimeout(remaining)
            if source_address: connection.bind(source_address)
            connection.connect(destination)
            return connection
        except OSError as exc:
            connection.close()
            error = exc
    raise error


class HTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, context, hostname, connect_ip=''):
        super().__init__(context=context)
        self.hostname = hostname
        self.connect_ip = str(ipaddress.ip_address(connect_ip)) if connect_ip else None

    def https_open(self, request):
        def factory(host, **kwargs):
            connection = http.client.HTTPSConnection(host, **kwargs)
            # Only the TCP destination changes. HTTPSConnection still checks
            # the original server name, certificate and SNI. Never redirect a proxy.
            override = self.connect_ip if connection.host.lower() == self.hostname.lower() else None
            connection._create_connection = functools.partial(connect, override=override)
            return connection
        return self.do_open(factory, request, context=self._context)
