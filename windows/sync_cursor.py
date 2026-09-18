"""Durable remote view. A cursor advances only with the view it describes."""
import ui_language
import copy
import time

FORMAT = 1
FULL_INTERVAL = 3600


def pull(request, saved, marker, decode, *, force=False, now=None):
    now = time.time() if now is None else now
    valid = (isinstance(saved, dict) and saved.get('format') == FORMAT
             and saved.get('marker') == marker and isinstance(saved.get('objects'), dict)
             and type(saved.get('cursor')) is int and saved['cursor'] >= 0)
    full = force or not valid or now - saved.get('full_at', 0) >= FULL_INTERVAL
    original = saved if valid else {}
    # Retrying a restore/restart never treats absent records as deletions.
    for attempt in range(2):
        remote = {} if full else copy.deepcopy(original['objects'])
        cursor = 0 if full else original['cursor']
        epoch = None if full else original.get('epoch')
        received = 0
        while True:
            before = cursor
            page = request('/v1/pull', {'after': cursor})
            generation = page.get('epoch')
            high = page.get('high_watermark')
            if ((epoch is not None and generation != epoch)
                    or (type(high) is int and high < cursor)):
                if attempt: raise ValueError(ui_language.t('Cloud ble startet på nytt under synkronisering. Prøv igjen; lokale data er beholdt.'))
                full = True
                break
            if generation is not None: epoch = generation
            items = page['items']
            if not isinstance(items, list): raise ValueError(ui_language.t('Ugyldig kontaktoversikt fra Cloud.'))
            for item in items:
                revision = item.get('revision')
                if type(revision) is not int or revision <= before:
                    raise ValueError(ui_language.t('Cloud sendte en ugyldig revisjon. Lokale data er beholdt.'))
                cursor = max(cursor, revision)
                value = decode(item)
                if value is not None: remote[value['key']] = value
            received += len(items)
            if not page.get('more'):
                return {'format': FORMAT, 'marker': marker, 'cursor': cursor,
                        'epoch': epoch, 'objects': remote,
                        'full_at': now if full else original['full_at']}, received
            if cursor <= before:
                raise ValueError(ui_language.t('Cloud sendte samme loggside flere ganger. Ingen kontakter er overskrevet.'))
    raise ValueError(ui_language.t('Cloud kunne ikke leses ferdig. Lokale data er beholdt.'))
