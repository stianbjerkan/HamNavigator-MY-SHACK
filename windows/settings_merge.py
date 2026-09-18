"""Merge Map settings by content, preserving complete saved service accounts."""
import ui_language
import base64
import copy
import json

MISSING = object()


def decode(files):
    if not isinstance(files, dict):
        raise ValueError(ui_language.t('Ugyldige kartinnstillinger.'))
    return {name: json.loads(base64.b64decode(raw, validate=True).decode('utf-8-sig'))
            for name, raw in files.items()}


def encode(files):
    return {name: base64.b64encode(json.dumps(value, ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode()).decode()
            for name, value in files.items()}


def _get(value, path):
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value


def _set(value, path, item):
    for part in path[:-1]:
        if item is MISSING:
            if not isinstance(value.get(part), dict):
                return
            value = value[part]
        else:
            value = value.setdefault(part, {})
    if item is MISSING:
        value.pop(path[-1], None)
    else:
        value[path[-1]] = copy.deepcopy(item)


def _filled(value):
    return value is not MISSING and value is not None and value != ''


def _tree(left, right, before=MISSING, path=(), conflicts=None):
    """Three-way merge; an existing Cloud profile initializes a new PC."""
    if conflicts is None:
        conflicts = []
    if left == right:
        return copy.deepcopy(left) if left is not MISSING else MISSING
    if isinstance(left, dict) and isinstance(right, dict):
        result = {}
        old = before if isinstance(before, dict) else {}
        for field in sorted(left.keys() | right.keys() | old.keys()):
            value = _tree(left.get(field, MISSING), right.get(field, MISSING),
                          old.get(field, MISSING), path + (field,), conflicts)
            if value is not MISSING:
                result[field] = value
        return result
    # Empty profiles from another installation are never a password deletion.
    field = path[-1].lower() if path else ''
    if ('password' in field or 'apikey' in field) and _filled(left) != _filled(right):
        return copy.deepcopy(left if _filled(left) else right)
    if before is not MISSING:
        if left == before:
            return copy.deepcopy(right) if right is not MISSING else MISSING
        if right == before:
            return copy.deepcopy(left) if left is not MISSING else MISSING
        conflicts.append('.'.join(path))
        return copy.deepcopy(left) if left is not MISSING else MISSING
    # First download: Cloud is the saved workspace, local defaults are not edits.
    return copy.deepcopy(right if right is not MISSING else left)


def _service(text, flags=(), identity=None, app=False):
    root = ('app',) if app else ('adifLog', 'text')
    fields = [root + (f,) for f in text]
    fields += [('adifLog', kind, name) for kind, name in flags]
    return fields, [root + (f,) for f in (identity or text)]


SERVICES = {
    'QRZ': _service(('qrzApiKey',), (('menu','buttonQRZCheckBox'), ('startup','loadQRZCheckBox'), ('qsolog','logQRZqsoCheckBox'))),
    'ClubLog': _service(('clubCall','clubEmail','clubPassword'), (('menu','buttonClubCheckBox'), ('startup','loadClubCheckBox'), ('qsolog','logClubqsoCheckBox'))),
    'LoTW': _service(('lotwLogin','lotwPassword','lotwTrusted','lotwStation'), (('menu','buttonLOTWCheckBox'), ('startup','loadLOTWCheckBox'), ('qsolog','logLOTWqsoCheckBox'))),
    'HRDLOG': _service(('HRDLOGCallsign','HRDLOGUploadCode'), (('qsolog','logHRDLOGqsoCheckBox'),)),
    'Cloudlog': _service(('CloudlogURL','CloudlogAPI','CloudlogStationProfileID'), (('qsolog','logCloudlogQSOCheckBox'),), ('CloudlogAPI',)),
    'eQSL': _service(('eQSLUser','eQSLPassword','eQSLNickname'), (('qsolog','logeQSLQSOCheckBox'), ('nickname','nicknameeQSLCheckBox'))),
    'HamCQ': _service(('HamCQApiKey',), (('qsolog','logHamCQqsoCheckBox'),)),
    **{name: _service(('lookupLogin'+suffix,'lookupPassword'+suffix), app=True)
       for name, suffix in (('QRZ-oppslag','Qrz'), ('CQ-oppslag','Cq'), ('QTH-oppslag','Qth'))},
}


def merge_map(local, remote, base=MISSING):
    """Return a portable Map file set and names of genuine conflicting fields.

    Keep each service's identity, credentials and switches together when one
    side has no account. Never combine credentials for two different accounts.
    Explicit conflict choices in Sync bypass this automatic merge.
    """
    left, right = decode(local), decode(remote)
    previous = decode(base) if isinstance(base, dict) else {}
    a, b = left.get('app-settings.json', {}), right.get('app-settings.json', {})
    old = previous.get('app-settings.json', {})
    selected = []
    conflicts = []
    for label, (fields, identities) in SERVICES.items():
        av = {'.'.join(p): _get(a, p) for p in fields if _get(a, p) is not MISSING}
        bv = {'.'.join(p): _get(b, p) for p in fields if _get(b, p) is not MISSING}
        ov = {'.'.join(p): _get(old, p) for p in fields if _get(old, p) is not MISSING}
        has_a = any(_filled(_get(a, p)) for p in identities)
        has_b = any(_filled(_get(b, p)) for p in identities)
        if has_a != has_b:
            chosen = av if has_a else bv
        else:
            credentials_a = {p: _get(a, p) for p in fields if p[:2] == ('adifLog','text') or p[0] == 'app'}
            credentials_b = {p: _get(b, p) for p in credentials_a}
            if has_a and credentials_a != credentials_b and av != ov and bv != ov:
                conflicts.append(label)
                chosen = av
            else:
                chosen = _tree(av, bv, ov if isinstance(base, dict) else MISSING, (label,), conflicts)
        selected.append((fields, chosen))
        for p in fields:
            _set(a, p, MISSING); _set(b, p, MISSING); _set(old, p, MISSING)
    merged = _tree(left, right, previous if isinstance(base, dict) else MISSING, (), conflicts)
    target = merged.setdefault('app-settings.json', {})
    for fields, chosen in selected:
        for p in fields:
            _set(target, p, chosen.get('.'.join(p), MISSING))
    return encode(merged), conflicts
