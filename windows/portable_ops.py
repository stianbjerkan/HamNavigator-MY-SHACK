"""POTA/SOTA references and opt-in activation tagging, without network uploads."""
import ui_language
import re

def references(q):
    for key in ('MY_SIG_INFO','SIG_INFO','MY_SOTA_REF','SOTA_REF'):
        value = str(q.get(key, '')).strip().upper()
        if not value:
            continue
        if 'SOTA' in key:
            valid = re.fullmatch(r'[A-Z0-9]+/[A-Z0-9]+-\d{3,}', value)
        elif q.get('MY_SIG' if key.startswith('MY_') else 'SIG', 'POTA').upper() == 'POTA':
            valid = re.fullmatch(r'[A-Z0-9]+-\d{4,}', value)
        else:
            continue
        if not valid:
            raise ValueError(ui_language.t('Ugyldig park-/toppreferanse: ')+value)
        q[key] = value
        if key in ('MY_SIG_INFO','SIG_INFO'):
            q['MY_SIG' if key.startswith('MY_') else 'SIG'] = 'POTA'
    return q

def activation_fields(row, activation):
    q = dict(row)
    stamp = q.get('QSO_DATE','') + q.get('TIME_ON','').ljust(6,'0')
    if not activation.get('active') or stamp[:8] != activation.get('date') or stamp < activation.get('start',''):
        return q
    for key in ('MY_SIG_INFO','MY_SOTA_REF','STATION_CALLSIGN','MY_GRIDSQUARE'):
        if activation.get(key) and not q.get(key):
            q[key] = activation[key]
    if q.get('MY_SIG_INFO') and not q.get('MY_SIG'):
        q['MY_SIG'] = 'POTA'
    return q

def select_log(qsos, program, role, ref='', date=''):
    if program not in ('pota','sota') or role not in ('activator','chaser'):
        raise ValueError(ui_language.t('Velg POTA/SOTA og aktivator/jeger.'))
    field = ('MY_' if role == 'activator' else '') + ('SIG_INFO' if program == 'pota' else 'SOTA_REF')
    sig = 'MY_SIG' if role == 'activator' else 'SIG'
    return [q for q in qsos if q.get(field) and (program != 'pota' or q.get(sig,'').upper() == 'POTA')
            and (not ref or q[field] == ref.upper()) and (not date or q.get('QSO_DATE') == date.replace('-',''))]
