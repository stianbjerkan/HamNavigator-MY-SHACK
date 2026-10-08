"""Bounded, anonymous aggregate request. No account credentials are transmitted."""
import json
import threading
import time
import urllib.request

URL = 'https://lb7yk.no/cloud/community'
_lock = threading.Lock()
_until = 0
_fetched = 0
_value = {'available': False}


def validate(data):
    if not isinstance(data, dict) or data.get('available') is not True:
        return {'available': False}
    total, active, age = (data.get(k) for k in ('registered', 'active', 'sample_age'))
    if (type(total) is not int or type(active) is not int or type(age) is not int
            or not 0 <= active <= total <= 1_000_000_000 or not 0 <= age <= 75
            or data.get('active_seconds') != 120):
        raise ValueError('Invalid community statistics')
    return {'available': True, 'registered': total, 'active': active,
            'sample_age': age, 'max_age': 75, 'active_seconds': 120}


def snapshot():
    global _until, _value, _fetched
    with _lock:
        now = time.monotonic()
        if now < _until:
            result = dict(_value)
            if result.get('available'):
                result['sample_age'] += int(now - _fetched)
            return result
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(urllib.request.Request(URL, headers={'Accept': 'application/json'}), timeout=5) as response:
                raw = response.read(4097)
                if len(raw) > 4096:
                    raise ValueError('Oversized community response')
                value = validate(json.loads(raw))
        except (OSError, ValueError):
            value = {'available': False}
        _fetched = time.monotonic()
        _value = value
        _until = _fetched + min(15, max(0, 75-value.get('sample_age', 0)))
        return dict(value)
