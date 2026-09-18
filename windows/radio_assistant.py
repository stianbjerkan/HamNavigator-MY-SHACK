"""Radioassistent: local Windows application with an optional local audio module."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import urllib.parse
from portable_ops import references, activation_fields, select_log
import portable_map
import webbrowser
import ui_language
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from callsign_audio import CallsignListener, list_devices
from package_support import program_defaults, prepare_bundle
from cloud_sync import Sync
from qso_sync import canonical as sync_contact, LOCAL_FIELDS

ROOT = Path(__file__).resolve().parent
RUNNING_VERSION = (ROOT/'VERSION').read_text().strip()
BACKEND_STOPPING = False
ACTIVE_POSTS = 0
BACKEND_CONDITION = threading.Condition()
MODULE_CATALOG = json.loads((ROOT / 'modules.json').read_text(encoding='utf-8'))
MODULE_IDS = [module['id'] for module in MODULE_CATALOG]
PORT = int(os.environ.get('RADIOASSISTENT_PORT', '18763'))
URL = f"http://127.0.0.1:{PORT}"
DATA_DIR = Path(os.environ.get('RADIOASSISTENT_DATA', str(Path(os.environ.get('APPDATA', str(ROOT))) / 'Radioassistent')))
LOCK = threading.RLock()
TOKEN = secrets.token_urlsafe(32)
DEFAULTS = {'settings': {'call': '', 'grid': '', 'udp_port': 2238, 'dx_host': '', 'dx_port': 7300, 'watch': '', 'radio_notes': '', 'mshv_path': ''}, 'qsos': [], 'repeaters': []}
DEFAULTS['settings']['modules'] = MODULE_IDS.copy()
DEFAULTS['settings']['gridtracker_path'] = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'GridTracker2/GridTracker2/GridTracker2.exe')
DEFAULTS['settings'].update(program_defaults(ROOT, DATA_DIR))
STATE = copy.deepcopy(DEFAULTS)
LIVE = {'udp': {'running': False, 'message': ui_language.t('Ikke startet'), 'last_seen': None, 'clients': {}, 'decodes': [], 'logged': 0}, 'dx': {'running': False, 'message': ui_language.t('Ikke tilkoblet'), 'spots': []}}
UDP_SOCKET = None
DX_STOP = threading.Event()
DX_THREAD = None
WEATHER = {}
WEATHER_LOCK = threading.Lock()
AUDIO = CallsignListener()
CLOUD = None
SHARED = None
SHARED_BASE = []

def refresh_shared():
    global SHARED_BASE
    if SHARED is not None:
        from shared_log import ID
        rows=SHARED.read()
        STATE['qsos']=[{**q,'id':q[ID]} for q in rows]
        SHARED_BASE=copy.deepcopy(rows)

SYNC_SETTINGS = ('call','grid','watch','radio_notes','modules')

def cloud_snapshot():
    with LOCK:
        refresh_shared()
        # Check all local QSO identities before constructing the upload dictionary.
        # A dictionary alone would silently discard conflicting duplicate rows.
        seen={};unique=[];duplicates=0
        for raw in STATE['qsos']:
            q=validate_qso(raw)
            identity=qso_key(q)
            content=sync_contact(q)
            if identity in seen:
                if seen[identity]!=content:
                    raise ValueError(ui_language.t('Duplikatkontroll: ')+q['CALL']+' '+q['QSO_DATE']+' '+q['TIME_ON']+ui_language.t(' finnes flere ganger med ulike opplysninger. Rett kontaktene i loggboken før synkronisering. Ingen versjon er overskrevet.'))
                duplicates+=1
            else:
                seen[identity]=content;unique.append(q)
        if duplicates:
            from cloud_sync import atomic
            stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            atomic(DATA_DIR/'cloud'/'duplicate-backups'/(stamp+'.json'),STATE)
            previous=STATE['qsos'];STATE['qsos']=unique
            try:persist()
            except Exception:STATE['qsos']=previous;raise
        result = {'setting/'+key:copy.deepcopy(STATE['settings'].get(key)) for key in SYNC_SETTINGS}
        import settings_transfer
        result.update(settings_transfer.snapshot(ROOT,DATA_DIR,STATE['settings']))
        for q in unique:
            import hashlib
            key = hashlib.sha256(json.dumps(qso_key(q)).encode()).hexdigest()
            result['qso/'+key] = sync_contact(q)
        for item in STATE['repeaters']:
            result['repeaters/'+item['id']] = copy.deepcopy(item)
        panel_file = DATA_DIR/'cloud-panels-pending.json'
        if not panel_file.exists(): panel_file = DATA_DIR/'panels.json'
        if panel_file.exists():
            layout = json.loads(panel_file.read_text(encoding='utf-8'))
            # Custom executable paths and arbitrary programs never leave this PC.
            result['panels/layout'] = {'version':1,'arrangement':layout.get('arrangement',0),'locked':bool(layout.get('locked')),
                'panels':[{'source':p.get('source') if p.get('source') in ('home','digital','hammap','gridtracker') else None} for p in layout.get('panels',[])][:24], 'programs':{}}
        return result

def cloud_apply(incoming, captured):
    global STATE
    with LOCK:
        before=copy.deepcopy(STATE)
        try:return _cloud_apply(incoming,captured)
        except Exception:
            STATE=before
            raise

def _cloud_apply(incoming, captured):
    applied=[]
    with LOCK:
        current=cloud_snapshot()
        import settings_transfer
        private_keys={'setting/preferences','map/preferences','digital/preferences'}
        for key,value in incoming.items():
            if current.get(key)!=captured.get(key) or value is None:continue
            if key.startswith('qso/'):validate_qso(value)
            elif key in private_keys:settings_transfer.validate(key,value)
            elif key.startswith('repeaters/'):validate_repeater(value)
        for key,value in incoming.items():
            if current.get(key)!=captured.get(key):continue
            kind,name=key.split('/',1)
            if kind=='qso':
                import hashlib
                existing=next((old for old in STATE['qsos'] if hashlib.sha256(json.dumps(qso_key(old)).encode()).hexdigest()==name),{})
                # Local record identity and native source evidence belong to this PC.
                local_fields={k:v for k,v in existing.items() if k in LOCAL_FIELDS}
                q=validate_qso({**sync_contact(value),**local_fields}) if value is not None else None
                if q and hashlib.sha256(json.dumps(qso_key(q)).encode()).hexdigest()!=name:continue
                STATE['qsos']=[old for old in STATE['qsos'] if hashlib.sha256(json.dumps(qso_key(old)).encode()).hexdigest()!=name]
                if q:STATE['qsos'].append(q)
            elif key in private_keys:
                settings_transfer.stage(key,value,ROOT,DATA_DIR,STATE['settings'])
            elif kind=='setting' and name in SYNC_SETTINGS:
                if name=='modules':
                    if not isinstance(value,list) or any(v not in MODULE_IDS for v in value):continue
                elif not isinstance(value,str) or len(value)>10000:continue
                if name=='grid' and value:grid_point(value)
                STATE['settings'][name]=value
            elif kind=='repeaters':
                if value is not None and (not isinstance(value,dict) or value.get('id')!=name):continue
                if value is not None:value=validate_repeater(value)
                STATE['repeaters']=[x for x in STATE['repeaters'] if x['id']!=name]
                if value:STATE['repeaters'].append(value)
            elif key=='panels/layout':
                if not isinstance(value,dict) or type(value.get('arrangement')) is not int or value['arrangement'] not in range(5):continue
                panes=value.get('panels',[])
                if not 1<=len(panes)<=24 or any(not isinstance(p,dict) or p.get('source') not in (None,'home','digital','hammap','gridtracker') for p in panes):continue
                from cloud_sync import atomic
                atomic(DATA_DIR/'cloud-panels-pending.json',{'version':1,'arrangement':value['arrangement'],'locked':bool(value.get('locked')),'panels':[{'source':p.get('source')} for p in panes],'programs':{}})
            else:continue
            applied.append(key)
        if applied:persist()
    return applied


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def persist():
    global SHARED_BASE
    if SHARED is not None:
        from shared_log import ID,normalize
        rows=[]
        for q in STATE['qsos']:
            row=normalize(q);row[ID]=q.get(ID) or q.get('id') or secrets.token_hex(16);rows.append(row)
        try:result=SHARED.commit(SHARED_BASE,rows)
        except Exception:
            from shared_log import atomic
            atomic(DATA_DIR/'log'/('my-shack-pending-'+secrets.token_hex(8)+'.json'),json.dumps({'before':SHARED_BASE,'after':rows},ensure_ascii=False))
            raise
        SHARED_BASE=copy.deepcopy(result)
        STATE['qsos']=[{**q,'id':q[ID]} for q in result]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / 'data.json'
    temp = DATA_DIR / 'data.tmp'
    temp.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), encoding='utf-8')
    if path.exists():
        shutil.copy2(path, DATA_DIR / 'data.previous.json')
    os.replace(temp, path)


def load_state():
    global STATE,SHARED
    prepare_bundle(ROOT, DATA_DIR)
    path = DATA_DIR / 'data.json'
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('qsos'), list) or not isinstance(data.get('repeaters'), list):
            raise ValueError(ui_language.t('Datafilen kan ikke leses. Originalfilen er beholdt.'))
        STATE = data
        STATE['settings'] = {**DEFAULTS['settings'], **data.get('settings', {})}
        for key,value in program_defaults(ROOT, DATA_DIR).items():
            if not Path(STATE['settings'].get(key,'')).is_file():
                STATE['settings'][key] = value
    if (ROOT/'BUNDLE.json').exists() or (DATA_DIR/'log/hamnavigator.adi').exists():
        from shared_log import SharedLog
        SHARED=SharedLog(DATA_DIR,ROOT)
        SHARED.initialize()
        refresh_shared()


GRID_RE = re.compile(r'^[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?$')


def grid_point(grid):
    grid = grid.strip().upper()
    if not GRID_RE.fullmatch(grid):
        raise ValueError(ui_language.t('Lokator må ha 4, 6 eller 8 tegn, for eksempel JO59, JO59JH eller JO59JH12.'))
    lon = (ord(grid[0]) - 65) * 20 - 180 + int(grid[2]) * 2
    lat = (ord(grid[1]) - 65) * 10 - 90 + int(grid[3])
    w, h = 2, 1
    if len(grid) >= 6:
        w, h = 2 / 24, 1 / 24
        lon += (ord(grid[4]) - 65) * w
        lat += (ord(grid[5]) - 65) * h
    if len(grid) == 8:
        w, h = w / 10, h / 10
        lon += int(grid[6]) * w
        lat += int(grid[7]) * h
    return {'lat': lat + h / 2, 'lon': lon + w / 2}


def point_grid(lat, lon):
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat < 90 and -180 <= lon < 180):
        raise ValueError(ui_language.t('Breddegrad må være fra −90 til under 90 og lengdegrad fra −180 til under 180.'))
    x, y = lon + 180, lat + 90
    a, b = int(x // 20), int(y // 10)
    x, y = x % 20, y % 10
    c, d = int(x // 2), int(y)
    e, f = min(23, int(x % 2 * 12)), min(23, int(y % 1 * 24))
    return f'{chr(65+a)}{chr(65+b)}{c}{d}{chr(65+e)}{chr(65+f)}'


def path_between(a, b):
    p, q = grid_point(a), grid_point(b)
    la, lb = math.radians(p['lat']), math.radians(q['lat'])
    dl = math.radians(q['lon'] - p['lon'])
    h = math.sin((lb-la)/2)**2 + math.cos(la)*math.cos(lb)*math.sin(dl/2)**2
    km = 6371.0088 * 2 * math.asin(math.sqrt(max(0, min(1, h))))
    bearing = (math.degrees(math.atan2(math.sin(dl)*math.cos(lb), math.cos(la)*math.sin(lb)-math.sin(la)*math.cos(lb)*math.cos(dl))) + 360) % 360
    return {'from': p, 'to': q, 'km': round(km, 1), 'bearing': round(bearing, 1) if km > .001 else None}


def band_for(freq):
    for low, high, name in [(1.8,2,'160m'),(3.5,4,'80m'),(5,5.5,'60m'),(7,7.3,'40m'),(10.1,10.15,'30m'),(14,14.35,'20m'),(18.068,18.168,'17m'),(21,21.45,'15m'),(24.89,24.99,'12m'),(28,29.7,'10m'),(50,54,'6m'),(70,71,'4m'),(144,148,'2m'),(222,225,'1.25m'),(420,450,'70cm'),(1240,1300,'23cm')]:
        if low <= freq <= high:
            return name
    return ''


def number(value, label, low, high):
    try:
        result = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        raise ValueError(f"{label}{ui_language.t(': skriv et tall.')}")
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label}{ui_language.t(': bruk en verdi mellom ')}{low}{ui_language.t(' og ')}{high}.")
    return result


def validate_qso(raw):
    raw = references(dict(raw))
    q = {str(k).upper(): str(v).strip() for k, v in raw.items() if k != 'id'}
    call = q.get('CALL', '').upper()
    if not re.fullmatch(r'[A-Z0-9/]{3,32}', call) or not any(c.isdigit() for c in call) or not any(c.isalpha() for c in call):
        raise ValueError(ui_language.t('Skriv et gyldig kallesignal med bokstaver og tall.'))
    q['CALL'] = call
    d, t = q.get('QSO_DATE', ''), q.get('TIME_ON', '')
    if len(t) == 4:
        t += '00'
    if not re.fullmatch(r'\d{8}', d) or not re.fullmatch(r'\d{6}', t):
        raise ValueError(ui_language.t('Kontakten må ha gyldig UTC-dato og klokkeslett.'))
    try:
        dt.datetime.strptime(d + t, '%Y%m%d%H%M%S')
    except ValueError:
        raise ValueError(ui_language.t('Ugyldig UTC-dato eller klokkeslett.'))
    q['TIME_ON'] = t
    if q.get('FREQ'):
        f = number(q['FREQ'], 'Frekvens i MHz', .001, 1000000)
        q['FREQ'] = format(f, '.9g')
        q['BAND'] = band_for(f) or q.get('BAND', '')
    if not q.get('FREQ') and not q.get('BAND'):
        raise ValueError(ui_language.t('Oppgi frekvens eller bånd.'))
    for key in ('MODE', 'SUBMODE', 'GRIDSQUARE', 'MY_GRIDSQUARE', 'STATION_CALLSIGN'):
        if q.get(key):
            q[key] = q[key].upper()
    if not re.fullmatch(r'[A-Z0-9+ -]{1,32}', q.get('MODE', '')):
        raise ValueError(ui_language.t('Oppgi modus.'))
    if q['MODE'] in ('FT4', 'JS8', 'PSK31', 'PSK63', 'PSK125'):
        submode = q['MODE']
        q['MODE'], q['SUBMODE'] = ('PSK' if submode.startswith('PSK') else 'MFSK'), submode
    if q.get('GRIDSQUARE'):
        grid_point(q['GRIDSQUARE'])
    q['id'] = str(raw.get('id') or secrets.token_hex(8))
    return q


def qso_key(q):
    return tuple(q.get(k, '').upper() for k in ('CALL','QSO_DATE','TIME_ON','BAND','MODE','SUBMODE','STATION_CALLSIGN','MY_SIG_INFO','SIG_INFO','MY_SOTA_REF','SOTA_REF'))


def parse_adif(text):
    records, record = [], {}
    pos = 0
    # Consume field lengths so literal <EOR> within a comment is preserved.
    tag = re.compile(r'<([A-Za-z0-9_]+)(?::(\d+)(?::[A-Za-z])?)?>')
    while True:
        match = tag.search(text, pos)
        if not match:
            break
        key, length = match.group(1).upper(), match.group(2)
        pos = match.end()
        if length is not None:
            end = pos + int(length)
            if end > len(text):
                raise ValueError(f"ADIF-feltet {key}{ui_language.t(' er avkortet. Ingen kontakter er importert.')}")
            record[key] = text[pos:end]
            pos = end
        elif key == 'EOH':
            record = {}
        elif key == 'EOR':
            if record:
                records.append(record)
            record = {}
    if record:
        raise ValueError(ui_language.t('ADIF-filen mangler avsluttende <EOR>. Ingen kontakter er importert.'))
    return records


def import_adif(text, live_activation=False):
    rows = parse_adif(text)
    added, duplicates, errors = 0, 0, []
    with LOCK:
        refresh_shared()
        keys = {qso_key(q) for q in STATE['qsos']}
        valid = []
        for i, row in enumerate(rows, 1):
            try:
                if live_activation:
                    row = activation_fields(row, STATE.get('portable', {}))
                q = validate_qso(row)
                key = qso_key(q)
                if key in keys:
                    duplicates += 1
                else:
                    valid.append(q)
                    keys.add(key)
                    added += 1
            except ValueError as exc:
                errors.append(f'Kontakt {i}: {exc}')
        if valid:
            STATE['qsos'].extend(valid)
            persist()
    return {'added': added, 'duplicates': duplicates, 'invalid': len(errors), 'errors': errors[:20]}


def ascii_text(text):
    text = text.replace('ø','o').replace('Ø','O').replace('æ','ae').replace('Æ','AE')
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return text.encode('ascii','replace').decode('ascii')


def export_adif(qsos):
    out = ['Radioassistent\n<ADIF_VER:5>3.1.6 <PROGRAMID:14>Radioassistent <EOH>\n']
    for q in qsos:
        row = []
        for key, value in q.items():
            if key == 'id' or not value or key.endswith('_INTL') or not re.fullmatch(r'[A-Z0-9_]+', key):
                continue
            value = ascii_text(str(value))
            row.append(f'<{key}:{len(value)}>{value}')
        out.append(' '.join(row) + ' <EOR>\n')
    return ''.join(out)


class Packet:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def read(self, fmt):
        size = struct.calcsize('>' + fmt)
        result = struct.unpack_from('>' + fmt, self.data, self.pos)[0]
        self.pos += size
        return result

    def string(self):
        size = self.read('I')
        if size == 0xffffffff:
            return ''
        if size > len(self.data) - self.pos:
            raise ValueError(ui_language.t('Avkortet UDP-pakke'))
        value = self.data[self.pos:self.pos+size].decode('utf-8', 'replace')
        self.pos += size
        return value


def decode_packet(data):
    # MSHV Simplified UDP Broadcast sends a plain ADIF record, without Qt framing.
    if data.lstrip(b'\xef\xbb\xbf \r\n\t').startswith(b'<'):
        adif = data.decode('utf-8-sig').strip()
        if not re.search(r'<CALL:\d+(?::[A-Za-z])?>', adif, re.I) or not re.search(r'<EOR>', adif, re.I):
            raise ValueError(ui_language.t('UDP-meldingen inneholder ingen fullstendig ADIF-kontakt.'))
        parse_adif(adif)
        return {'kind': 12, 'client': 'MSHV (ADIF)' if re.search(r'<PROGRAMID:4>MSHV', adif, re.I) else 'ADIF UDP', 'received': utcnow(), 'adif': adif, 'format': 'adif'}
    p = Packet(data)
    if p.read('I') != 0xadbccbda:
        raise ValueError(ui_language.t('Ukjent UDP-format'))
    schema = p.read('I')
    if schema not in (2, 3):
        raise ValueError(ui_language.t('Ukjent UDP-versjon'))
    kind, client = p.read('I'), p.string()
    event = {'kind': kind, 'client': client, 'received': utcnow(), 'schema': schema}
    if kind == 0 and p.pos < len(data):
        event['max_schema'] = p.read('I')
        if p.pos < len(data):
            event['version'] = p.string()
    elif kind == 1:
        event.update(freq=p.read('Q') / 1e6, mode=p.string(), dx_call=p.string(), report=p.string(), tx_mode=p.string(), tx_enabled=p.read('?'), transmitting=p.read('?'), decoding=p.read('?'), rx_df=p.read('I'), tx_df=p.read('I'), call=p.string(), grid=p.string(), dx_grid=p.string())
    elif kind == 2:
        event.update(new=p.read('?'), milliseconds=p.read('I'), snr=p.read('i'), dt=p.read('d'), df=p.read('I'), mode=p.string(), message=p.string(), low_confidence=p.read('?'))
        event['off_air'] = p.read('?') if p.pos < len(data) else False
    elif kind == 12:
        event['adif'] = p.string()
    return event


def udp_loop(sock):
    while UDP_SOCKET is sock:
        try:
            data, _ = sock.recvfrom(65535)
            event = decode_packet(data)
            with LOCK:
                u = LIVE['udp']
                u['last_seen'] = event['received']
                kind, client = event['kind'], event['client']
                if kind not in (0, 1, 2, 3, 6, 12):
                    continue
                u['source'] = client
                u['message'] = ui_language.t('Mottar fra ') + client
                if kind == 1:
                    u['clients'][client] = event
                elif kind == 2:
                    event['freq'] = u['clients'].get(client, {}).get('freq')
                    event['operating_mode'] = u['clients'].get(client, {}).get('mode', '')
                    u['decodes'].insert(0, event)
                    del u['decodes'][300:]
                elif kind == 12:
                    if SHARED is not None and any(q.get('APP_HAMNAVIGATOR_SHARED')=='Y' for q in parse_adif(event['adif'])):
                        # Digital commits directly to the shared file; its UDP event is informational.
                        continue
                    result = import_adif(event['adif'], live_activation=True)
                    u['logged'] += result['added']
                    if result['invalid']:
                        u['message'] = ui_language.t('En kontakt fra ') + client + ui_language.t(' kunne ikke importeres: ') + result['errors'][0]
                elif kind == 3:
                    u['decodes'] = [r for r in u['decodes'] if r['client'] != client]
                elif kind == 6:
                    u['clients'].pop(client, None)
                    u['message'] = client + ui_language.t(' er avsluttet')
        except socket.timeout:
            continue
        except OSError:
            break
        except (ValueError, struct.error, UnicodeError) as exc:
            with LOCK:
                LIVE['udp']['message'] = ui_language.t('En UDP-melding kunne ikke leses: ') + str(exc)


def set_udp(start, port=2238):
    global UDP_SOCKET
    with LOCK:
        if UDP_SOCKET:
            old, UDP_SOCKET = UDP_SOCKET, None
            old.close()
        LIVE['udp'].update(running=False, message=ui_language.t('Stoppet'), last_seen=None, clients={})
        if start:
            port = int(number(port, 'UDP-port', 1024, 65535))
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                sock.close()
                raise ValueError(f"UDP-port {port}{ui_language.t(' er opptatt. Velg en annen port i begge programmene.')}")
            sock.settimeout(1)
            UDP_SOCKET = sock
            LIVE['udp'].update(running=True, port=port, message=ui_language.t('Lytter – venter på HamNavigator'))
            threading.Thread(target=udp_loop, args=(sock,), daemon=True).start()
    return {'ok': True}


def parse_spot(line):
    match = re.search(r'DX de\s+([A-Za-z0-9/\-]+):?\s+(\d+(?:\.\d+)?)\s+([A-Za-z0-9/]+)\s+(.*)', line)
    if not match:
        return None
    spotter, freq, call, comment = match.groups()
    return {'id': secrets.token_hex(6), 'spotter': spotter, 'freq': float(freq)/1000, 'call': call.upper(), 'comment': comment.strip(), 'received': utcnow(), 'band': band_for(float(freq)/1000)}


def dx_loop(host, port, call, stop):
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.settimeout(1)
            with LOCK:
                LIVE['dx'].update(message=ui_language.t('Tilkoblet – venter på spots'))
            # Standard DX-cluster login is the station callsign, once connected.
            sock.sendall((call + '\r\n').encode('ascii'))
            buffer = ''
            while not stop.is_set():
                try:
                    data = sock.recv(8192)
                except socket.timeout:
                    continue
                if not data:
                    break
                # Ignore common telnet IAC negotiation sequences.
                data = re.sub(rb'\xff[\xfb-\xfe].', b'', data)
                buffer += data.decode('utf-8', 'replace').replace('\r', '\n')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    spot = parse_spot(line)
                    if spot:
                        with LOCK:
                            LIVE['dx']['spots'].insert(0, spot)
                            del LIVE['dx']['spots'][300:]
                            LIVE['dx']['message'] = ui_language.t('Mottar DX-spots')
                buffer = buffer[-16000:]
    except OSError as exc:
        with LOCK:
            LIVE['dx']['message'] = ui_language.t('Kunne ikke koble til: ') + str(exc)
    finally:
        with LOCK:
            LIVE['dx']['running'] = False
            if not LIVE['dx']['message'].startswith(ui_language.t('Kunne ikke')):
                LIVE['dx']['message'] = ui_language.t('Frakoblet')


def set_dx(start):
    global DX_THREAD, DX_STOP
    if not start:
        DX_STOP.set()
        return {'ok': True}
    if DX_THREAD and DX_THREAD.is_alive():
        raise ValueError(ui_language.t('En tilkobling er allerede aktiv eller avsluttes. Vent litt og prøv igjen.'))
    s = STATE['settings']
    host = s['dx_host'].strip()
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', host):
        raise ValueError(ui_language.t('Lagre vertsnavnet til din DX-cluster under Min stasjon først.'))
    call = s['call'].upper()
    if not re.fullmatch(r'[A-Z0-9/]{3,32}', call):
        raise ValueError(ui_language.t('Lagre ditt kallesignal under Min stasjon først.'))
    port = int(number(s['dx_port'], 'DX-port', 1, 65535))
    DX_STOP = threading.Event()
    with LOCK:
        LIVE['dx'].update(running=True, message=ui_language.t('Kobler til …'))
    DX_THREAD = threading.Thread(target=dx_loop, args=(host, port, call, DX_STOP), daemon=True)
    DX_THREAD.start()
    return {'ok': True}


def fetch_weather():
    global WEATHER
    with WEATHER_LOCK:
        if WEATHER and time.time() - WEATHER['fetched_epoch'] < 600:
            return WEATHER
        result = {'fetched': utcnow(), 'fetched_epoch': time.time(), 'errors': []}
        for key, url in [('kp','https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json'),('flux','https://services.swpc.noaa.gov/products/summary/10cm-flux.json')]:
            try:
                req = urllib.request.Request(url, headers={'User-Agent':'Radioassistent/1.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    rows = json.load(response)
                if isinstance(rows, dict):
                    rows = [rows]
                elif rows and isinstance(rows[0], list):
                    rows = [dict(zip(rows[0], row)) for row in rows[1:]]
                rows = sorted(rows, key=lambda r:r.get('time_tag',''))
                field = 'Kp' if key == 'kp' else 'flux'
                valid = [r for r in rows if r.get(field) is not None]
                latest = valid[-1]
                result[key] = {'value': float(latest[field]), 'time': latest['time_tag'], 'source': url}
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                result['errors'].append(f'{key}: {exc}')
        WEATHER = result
        return result


def settings_update(raw):
    s = {k: raw.get(k, STATE['settings'].get(k, v)) for k,v in DEFAULTS['settings'].items()}
    for key in ('call','grid','watch'):
        s[key] = str(s[key]).strip().upper()
    if s['call'] and not re.fullmatch(r'[A-Z0-9/]{3,32}', s['call']):
        raise ValueError(ui_language.t('Ugyldig kallesignal.'))
    if s['grid']:
        grid_point(s['grid'])
    for k in ('udp_port','dx_port'):
        s[k] = int(number(s[k], 'Port', 1024 if k == 'udp_port' else 1, 65535))
    s['radio_notes'] = str(s['radio_notes'])[:30000]
    s['dx_host'] = str(s['dx_host']).strip()[:253]
    s['mshv_path'] = str(s['mshv_path']).strip().strip('"')
    if s['mshv_path']:
        mshv_executable(s['mshv_path'])
    s['gridtracker_path'] = str(s['gridtracker_path']).strip().strip('"')
    if s['gridtracker_path']:
        gridtracker_executable(s['gridtracker_path'])
    s['modules'] = validate_modules(s['modules'])
    with LOCK:
        STATE['settings'] = s
        persist()
    return {'ok': True}


def validate_modules(value):
    if not isinstance(value, list) or any(not isinstance(m, str) or m not in MODULE_IDS for m in value):
        raise ValueError(ui_language.t('Velg moduler fra listen i appen.'))
    return [m for m in MODULE_IDS if m in value]


def modules_update(value):
    selected = validate_modules(value)
    with LOCK:
        previous = STATE['settings'].get('modules', MODULE_IDS.copy())
        STATE['settings']['modules'] = selected
        try:
            persist()
        except Exception:
            STATE['settings']['modules'] = previous
            raise
    if 'listener' not in selected:
        AUDIO.stop()
    return {'modules': selected}


def validate_repeater(raw):
    row = {k: str(raw.get(k, '')).strip() for k in ('id','name','call','grid','rx','shift','tone','notes','checked')}
    if not row['name']:
        raise ValueError(ui_language.t('Oppgi navn på repeateren.'))
    row['rx'] = number(row['rx'], 'Mottaksfrekvens i MHz', .001, 1000000)
    row['shift'] = number(row['shift'] or 0, 'Senderskift i MHz', -10000, 10000)
    if row['rx'] + row['shift'] <= 0:
        raise ValueError(ui_language.t('Sendefrekvensen må være positiv.'))
    row['grid'] = row['grid'].upper()
    if row['grid']:
        row['point'] = grid_point(row['grid'])
    if row['checked']:
        dt.date.fromisoformat(row['checked'])
    row['call'] = row['call'].upper()
    row['id'] = row['id'] or secrets.token_hex(8)
    return row


def repeater_save(raw):
    row = validate_repeater(raw)
    with LOCK:
        STATE['repeaters'] = [r for r in STATE['repeaters'] if r['id'] != row['id']] + [row]
        persist()
    return {'ok': True}


def python_windowless():
    path = Path(sys.executable).with_name('pythonw.exe')
    return str(path if path.exists() else sys.executable)


def mshv_executable(value):
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or not re.fullmatch(r'MSHV(?:_WIN(?:32|64))?\.exe', path.name, re.I):
        raise ValueError(ui_language.t('Velg den eksterne dekoderens programfil under Min stasjon.'))
    return path


def open_mshv():
    path = mshv_executable(STATE['settings'].get('mshv_path', ''))
    if not LIVE['udp']['running']:
        set_udp(True, STATE['settings']['udp_port'])
    if not open_desktop('mshv'):
        subprocess.Popen([str(path)], cwd=str(path.parent))
    return {'ok': True}


def gridtracker_executable(value):
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or not re.fullmatch(r'GridTracker2?\.exe', path.name, re.I):
        raise ValueError(ui_language.t('Velg det eksterne kartprogrammets programfil under Min stasjon.'))
    return path


def open_desktop(panel='home', *, resume=True):
    if panel not in ('home', 'mshv', 'gridtracker', 'both', 'digital', 'hammap', 'hamnavigator'):
        raise ValueError(ui_language.t('Ukjent programfane.'))
    runtime = ROOT / '.venv-desktop/Scripts/pythonw.exe'
    if not runtime.is_file():
        runtime = ROOT / 'runtime/pythonw.exe'
    if not runtime.is_file():
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR/'desktop.log').open('a', encoding='utf-8') as log:
        subprocess.Popen([str(runtime), str(ROOT/'desktop_host.py'), '--panel', panel,
                          *([] if resume else ['--no-resume'])],
            cwd=str(ROOT), stdout=log, stderr=log, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return True


def open_app():
    if open_desktop():
        return
    for base in (os.environ.get('ProgramFiles(x86)', ''), os.environ.get('ProgramFiles', ''), os.environ.get('LOCALAPPDATA','')):
        edge = Path(base) / 'Microsoft/Edge/Application/msedge.exe'
        if edge.exists():
            subprocess.Popen([str(edge), '--app=' + URL, '--window-size=1250,850'])
            return
    webbrowser.open(URL)


def widget():
    import tkinter as tk
    root = tk.Tk()
    root.title('UTC · HamNavigator MY SHACK')
    root.configure(bg='#101b29')
    root.resizable(False, False)
    root.attributes('-topmost', True)
    root.geometry(f'280x172+{max(0, root.winfo_screenwidth()-310)}+35')
    tk.Label(root, text='UTC  /  RADIOASSISTENT', fg='#83dbc4', bg='#101b29', font=('Segoe UI',10)).pack(pady=(12,0))
    clock = tk.Label(root, fg='white', bg='#101b29', font=('Consolas',32))
    clock.pack()
    date = tk.Label(root, fg='#a9bacd', bg='#101b29', font=('Segoe UI',10))
    date.pack()
    tk.Button(root, text=ui_language.t('Åpne radioassistent  →'), command=open_app, bg='#23394b', fg='white', relief='flat', padx=18, pady=5).pack(pady=9)
    def tick():
        now = dt.datetime.now(dt.timezone.utc)
        clock.config(text=now.strftime('%H:%M:%S'))
        date.config(text=now.strftime('%d.%m.%Y'))
        root.after(200, tick)
    tick()
    root.mainloop()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, status=200, content_type='application/json; charset=utf-8', filename=None):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8') if content_type.startswith('application/json') else (value.encode('utf-8') if isinstance(value,str) else value)
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{PORT}', f'localhost:{PORT}')

    def do_GET(self):
        if not self.valid_host():
            return self.send({'error':ui_language.t('Ugyldig vert')}, 403)
        path = self.path.split('?')[0]
        try:
            if path == '/api/language':
                return self.send({'language':ui_language.get()})
            if path == '/api/health':
                return self.send({'app':'HamNavigator MY SHACK','version':RUNNING_VERSION,'root':str(ROOT),'pid':os.getpid(),'can_stop':True,'stopping':BACKEND_STOPPING})
            if path == '/api/cloud/status':
                return self.send(CLOUD.view() if CLOUD else {'message':ui_language.t('Start programmet på nytt for å aktivere skyklienten.')})
            if path == '/language.js':
                return self.send((ROOT/'language.js').read_text(encoding='utf-8'),content_type='text/javascript; charset=utf-8')
            if path in tuple(f'/languages/{code}/{name}.js' for code in ('en','sv') for name in ('app','cloud','operations','admin','listener','portable','portable-map')):
                return self.send((ROOT/path[1:]).read_text(encoding='utf-8'),content_type='text/javascript; charset=utf-8')
            if path == '/cloud.js':
                return self.send((ROOT/'cloud.js').read_text(encoding='utf-8'),content_type='text/javascript; charset=utf-8')
            if path == '/operations.js':
                return self.send((ROOT/'operations.js').read_text(encoding='utf-8'),content_type='text/javascript; charset=utf-8')
            if path == '/admin.js':
                return self.send((ROOT/'admin.js').read_text(encoding='utf-8'),content_type='text/javascript; charset=utf-8')
            if path == '/':
                return self.send((ROOT/(f'languages/{ui_language.get()}/app.html' if ui_language.get() in ('en','sv') else 'app.html')).read_text(encoding='utf-8').replace('__TOKEN__', TOKEN), content_type='text/html; charset=utf-8')
            if path in ('/app.js','/app.css','/listener.js','/portable.js','/portable-map.js','/vendor/ol.js','/vendor/ol.css'):
                return self.send((ROOT/path[1:]).read_text(encoding='utf-8'), content_type='text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
            if path == '/api/state':
                if not CLOUD or not CLOUD.authorized:
                    return self.send({'settings':{},'qsos':[],'repeaters':[],'module_catalog':ui_language.modules(MODULE_CATALOG),'login_required':True})
                with LOCK:
                    refresh_shared()
                    return self.send({**copy.deepcopy(STATE), 'data_dir': str(DATA_DIR), 'module_catalog': ui_language.modules(MODULE_CATALOG)})
            if path.startswith('/api/') and (not CLOUD or not CLOUD.authorized):
                return self.send({'error':ui_language.t('Logg inn for å bruke HamNavigator.')},401)
            if path == '/api/portable-map':
                return self.send(portable_map.query(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))))
            if path == '/api/live':
                with LOCK:
                    revision = ''
                    if SHARED and SHARED.path.exists():
                        stat = SHARED.path.stat()
                        revision = str(stat.st_mtime_ns)+':'+str(stat.st_size)
                    view=copy.deepcopy(LIVE)
                    for key in ('udp','dx'):view[key]['message']=ui_language.t(view[key]['message'])
                    return self.send({**view, 'log_revision':revision})
            if path == '/api/audio/status':
                return self.send(AUDIO.snapshot())
            if path == '/api/weather':
                return self.send(fetch_weather())
            if path == '/api/export':
                with LOCK:
                    refresh_shared()
                    args = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
                    qsos = STATE['qsos']
                    if args.get('program'):
                        qsos = select_log(qsos, args['program'], args.get('role','activator'), args.get('ref',''), args.get('date',''))
                    return self.send(export_adif(qsos), content_type='text/plain; charset=us-ascii', filename=((args.get('program') or 'hamnavigator')+'.adi'))
            if path == '/api/backup':
                with LOCK:
                    refresh_shared()
                    return self.send({**STATE,'backup_created':utcnow()}, filename='hamnavigator-backup.json')
            self.send({'error':ui_language.t('Ikke funnet')}, 404)
        except Exception as exc:
            self.send({'error':str(exc)}, 500)

    def do_POST(self):
        global ACTIVE_POSTS
        with BACKEND_CONDITION:
            if BACKEND_STOPPING:return self.send({'error':ui_language.t('HamNavigator avsluttes. Prøv igjen etter omstart.')},503)
            ACTIVE_POSTS+=1
        try:self.handle_post()
        finally:
            with BACKEND_CONDITION:
                ACTIVE_POSTS-=1;BACKEND_CONDITION.notify_all()

    def handle_post(self):
        global BACKEND_STOPPING
        if not self.valid_host() or not secrets.compare_digest(self.headers.get('X-Radio-Token', ''), TOKEN):
            return self.send({'error':ui_language.t('Last appen på nytt og prøv igjen.')}, 403)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length < 0 or length > 20_000_000:
                raise ValueError(ui_language.t('Filen er for stor (maks 20 MB).'))
            raw = json.loads(self.rfile.read(length) or b'{}')
            path = self.path
            if not path.startswith('/api/cloud/') and path not in ('/api/backend/stop','/api/audio/stop','/api/language') and (not CLOUD or not CLOUD.authorized):
                return self.send({'error':ui_language.t('Logg inn for å bruke HamNavigator.')},401)
            result = {'ok':True}
            if path=='/api/language':
                result={'ok':True,'language':ui_language.select(raw.get('language'))}
            elif path=='/api/backend/stop':
                with BACKEND_CONDITION:BACKEND_STOPPING=True
                threading.Thread(target=stop_backend,args=(self.server,),daemon=True).start()
            elif path.startswith('/api/cloud/'):
                if CLOUD is None:raise ValueError(ui_language.t('Skyklienten er ikke startet.'))
                action=path.rsplit('/',1)[-1]
                if action=='connect':result=CLOUD.connect(raw)
                elif action=='check':result=CLOUD.check_connection(raw)
                elif action=='import-connection':result=CLOUD.import_connection(raw)
                elif action in ('request-reset','reset-password','resend-verification','verify-email'):result=CLOUD.email_action(action,raw)
                elif action=='verify':result=CLOUD.verify()
                elif action=='admin-users':result=CLOUD.admin_users(raw)
                elif action=='recovery':result=CLOUD.recovery()
                elif action=='disconnect':result=CLOUD.disconnect()
                elif action=='auto':result=CLOUD.auto(raw.get('enabled',False))
                elif action=='sync':result=CLOUD.sync(raw.get('choices'))
                elif action=='deliveries':result=CLOUD.deliveries()
                elif action in ('overview','backups','backup-preview','backup-restore','diagnostics','delivery-choice'):
                    if not CLOUD.authorized:raise ValueError(ui_language.t('Logg inn først.'))
                    if action=='overview':result=CLOUD.ops.overview()
                    elif action=='backups':result=CLOUD.ops.backup_items()
                    elif action=='backup-preview':result=CLOUD.ops.preview(raw.get('id'))
                    elif action=='backup-restore':
                        if raw.get('confirm') is not True:raise ValueError(ui_language.t('Kontroller sikkerhetskopien før gjenoppretting.'))
                        result=CLOUD.ops.restore(raw.get('id'))
                    elif action=='diagnostics':result=CLOUD.ops.diagnostics()
                    else:result=CLOUD.request('/v1/delivery/account-resolve',raw)
                else:raise ValueError(ui_language.t('Ukjent skyhandling.'))
            elif path == '/api/settings':
                result = settings_update(raw)
            elif path == '/api/modules':
                result = modules_update(raw.get('modules'))
            elif path == '/api/audio/devices':
                result = {'devices':list_devices()}
            elif path == '/api/audio/start':
                if 'listener' not in STATE['settings'].get('modules',MODULE_IDS):
                    raise ValueError(ui_language.t('Velg Kallesignallytter under Velg moduler først.'))
                result = AUDIO.start(raw)
            elif path == '/api/audio/stop':
                result = AUDIO.stop()
            elif path == '/api/audio/heartbeat':
                result = AUDIO.touch(raw.get('session'))
            elif path == '/api/audio/file':
                result = AUDIO.analyze_file(raw.get('audio',''),raw.get('language','en'),bool(raw.get('filter',True)))
            elif path == '/api/audio/clear':
                result = AUDIO.clear()
            elif path == '/api/audio/clip':
                return self.send(AUDIO.clip(raw.get('id','')),content_type='audio/wav')
            elif path == '/api/portable-map/update':
                result = portable_map.update_catalogue()
            elif path == '/api/portable':
                with LOCK:
                    if raw.get('active'):
                        now = dt.datetime.now(dt.timezone.utc)
                        values = references({k:str(raw.get(k,'')).strip().upper() for k in ('MY_SIG_INFO','MY_SOTA_REF')})
                        if not any(values.values()):
                            raise ValueError(ui_language.t('Oppgi egen park eller topp før aktivering.'))
                        STATE['portable'] = {**values, 'active':True, 'date':now.strftime('%Y%m%d'), 'start':now.strftime('%Y%m%d%H%M%S'), 'STATION_CALLSIGN':STATE['settings']['call'], 'MY_GRIDSQUARE':STATE['settings']['grid']}
                    else:
                        STATE['portable'] = {**STATE.get('portable',{}), 'active':False}
                    persist()
            elif path == '/api/qso':
                with LOCK:
                    refresh_shared()
                    original=next((q for q in STATE['qsos'] if q['id']==raw.get('id')), {})
                    expected=raw.pop('_expected',None)
                    if raw.get('id') and (not original or (expected is not None and expected!=original)):
                        raise ValueError(ui_language.t('Kontakten er endret i et annet vindu. Åpne kontakten på nytt før du lagrer.'))
                    q = validate_qso(activation_fields(raw, STATE.get('portable',{})) if not raw.get('id') else {**original,**raw})
                    if not raw.get('id') and any(qso_key(x) == qso_key(q) for x in STATE['qsos']):
                        raise ValueError(ui_language.t('Denne kontakten finnes allerede i loggen.'))
                    STATE['qsos'] = [x for x in STATE['qsos'] if x['id'] != q['id']] + [q]
                    persist()
            elif path in ('/api/qso/delete','/api/repeater/delete'):
                key = 'qsos' if path.startswith('/api/qso') else 'repeaters'
                with LOCK:
                    refresh_shared()
                    if key=='qsos' and '_expected' in raw:
                        original=next((q for q in STATE[key] if q['id']==raw.get('id')),None)
                        if original!=raw['_expected']:
                            raise ValueError(ui_language.t('Kontakten er endret i et annet vindu. Oppdater loggboken før du sletter.'))
                    STATE[key] = [x for x in STATE[key] if x['id'] != raw.get('id')]
                    persist()
            elif path == '/api/repeater':
                result = repeater_save(raw)
            elif path == '/api/import':
                result = import_adif(raw.get('text',''))
            elif path in ('/api/restore','/api/restore-preview'):
                data = raw.get('data')
                if not isinstance(data,dict) or not isinstance(data.get('qsos'),list) or not isinstance(data.get('repeaters'),list):
                    raise ValueError(ui_language.t('Dette er ikke en gyldig sikkerhetskopi for HamNavigator MY SHACK.'))
                # Restore merges contacts and favourites; current settings are retained.
                qs = [validate_qso(q) for q in data['qsos']]
                repeaters = [validate_repeater(r) for r in data['repeaters']]
                with LOCK:
                    refresh_shared()
                    keys = {qso_key(q) for q in STATE['qsos']}
                    missing={qso_key(q) for q in qs}-keys
                    if path=='/api/restore-preview':
                        return self.send({'contacts':len({qso_key(q) for q in qs}), 'current':len(keys),'add':len(missing),'date':str(data.get('backup_created',ui_language.t('Ukjent dato')))[:64]})
                    if raw.get('confirm') is not True:raise ValueError(ui_language.t('Kontroller sikkerhetskopien før gjenoppretting.'))
                    previous=copy.deepcopy(STATE)
                    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
                    CLOUD.save_private(DATA_DIR/'restore-backups'/(stamp+'.json'),previous)
                    count = 0
                    for q in qs:
                        if qso_key(q) not in keys:
                            q['id'] = secrets.token_hex(8)
                            STATE['qsos'].append(q)
                            keys.add(qso_key(q))
                            count += 1
                    for r in repeaters:
                        if not any(old['id']==r['id'] for old in STATE['repeaters']):STATE['repeaters'].append(r)
                    try:persist()
                    except Exception:
                        STATE.clear();STATE.update(previous);raise
                result = {'added':count, 'repeaters':len(repeaters)}
            elif path == '/api/udp':
                result = set_udp(bool(raw.get('start')), STATE['settings']['udp_port'])
            elif path == '/api/mshv/open':
                result = open_mshv()
            elif path == '/api/desktop/open':
                panel = raw.get('panel', 'home')
                if panel in ('gridtracker', 'both'):
                    gridtracker_executable(STATE['settings'].get('gridtracker_path', ''))
                if panel in ('mshv', 'both'):
                    mshv_executable(STATE['settings'].get('mshv_path', ''))
                if not open_desktop(panel):
                    raise ValueError(ui_language.t('Windows-rammen er ikke installert. Se RADIOROM.md.'))
            elif path == '/api/dx':
                result = set_dx(bool(raw.get('start')))
            elif path == '/api/path':
                result = path_between(raw.get('from',''),raw.get('to',''))
            elif path == '/api/grid':
                result = {'grid':point_grid(raw.get('lat'),raw.get('lon'))}
            elif path == '/api/widget':
                subprocess.Popen([python_windowless(), str(ROOT/'radio_assistant.py'), '--widget'], creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            else:
                return self.send({'error':ui_language.t('Ikke funnet')},404)
            self.send(result)
        except (ValueError, TypeError, KeyError) as exc:
            if getattr(CLOUD,'ops',None):
                try:CLOUD.ops.history.record('App',exc)
                except OSError:pass
            self.send({'error':str(exc)},400)
        except Exception as exc:
            if getattr(CLOUD,'ops',None):
                try:CLOUD.ops.history.record('App',exc)
                except OSError:pass
            self.send({'error':str(exc)},500)


def backend_info():
    try:
        with urllib.request.urlopen(URL+'/api/health', timeout=1) as response:
            return json.load(response)
    except Exception:return None

def healthy():
    info=backend_info()
    return bool(info and info.get('app')=='HamNavigator MY SHACK' and info.get('version')==RUNNING_VERSION and info.get('root')==str(ROOT) and not info.get('stopping'))

def stop_backend(server):
    global BACKEND_STOPPING
    if CLOUD:CLOUD.stop.set()
    with BACKEND_CONDITION:BACKEND_CONDITION.wait_for(lambda:ACTIVE_POSTS==0)
    # Finish any sync that was already in progress before flushing local state.
    lock=CLOUD.lock if CLOUD else LOCK
    try:
        with lock:
            set_udp(False,STATE['settings']['udp_port']);DX_STOP.set();AUDIO.stop()
            with LOCK:refresh_shared();persist()
            server.shutdown()
    except Exception as exc:
        # Keep this process/data available if the final disk flush fails.
        with BACKEND_CONDITION:BACKEND_STOPPING=False
        if CLOUD:
            CLOUD.config['automatic']=False
            CLOUD.status['message']=ui_language.t('Kunne ikke avslutte og lagre: ')+str(exc)
        with (DATA_DIR/'startup.log').open('a',encoding='utf-8') as log:log.write(ui_language.t('Avslutning feilet: ')+str(exc)+'\n')

def stop_previous_backend(info):
    if not info or info.get('app') not in ('Radioassistent','HamNavigator MY SHACK'):return
    if not info.get('can_stop'):
        raise RuntimeError(ui_language.t('En eldre HamNavigator-bakgrunnstjeneste kjører fortsatt. Avslutt HamNavigator og start Windows på nytt én gang for å ta i bruk oppdateringen. Loggboken beholdes.'))
    with urllib.request.urlopen(URL,timeout=3) as response:
        token=re.search(r'name="radio-token" content="([^"]+)"',response.read().decode()).group(1)
    request=urllib.request.Request(URL+'/api/backend/stop',b'{}',headers={'Content-Type':'application/json','X-Radio-Token':token})
    with urllib.request.urlopen(request,timeout=5) as response:json.load(response)
    for _ in range(100):
        if backend_info() is None:return
        time.sleep(.1)
    raise RuntimeError(ui_language.t('HamNavigator lagrer fortsatt data før omstart. Prøv igjen om litt.'))


def main():
    global CLOUD
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', action='store_true')
    parser.add_argument('--widget', action='store_true')
    parser.add_argument('--hamnavigator', action='store_true')
    parser.add_argument('--no-resume', action='store_true', help=ui_language.t('Åpne etter oppdatering uten å gjenoppta radio'))
    args = parser.parse_args()
    if args.server:
        load_state()
        CLOUD=Sync(DATA_DIR,cloud_snapshot,cloud_apply)
        CLOUD.start()
        server = ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
        server.daemon_threads = True
        try:server.serve_forever()
        finally:server.server_close()
    else:
        if not healthy():
            stop_previous_backend(backend_info())
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with (DATA_DIR/'startup.log').open('a',encoding='utf-8') as log:
                subprocess.Popen([python_windowless(),str(ROOT/'radio_assistant.py'),'--server'], stdout=log,stderr=log, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            for _ in range(60):
                if healthy():
                    break
                time.sleep(.15)
            else:
                raise RuntimeError(f"{ui_language.t('Kunne ikke starte HamNavigator MY SHACK. Se ')}{DATA_DIR / 'startup.log'}")
        if args.no_resume:
            if not open_desktop(resume=False):
                raise RuntimeError(ui_language.t('Windows-radiorommet er ikke installert.'))
        elif args.hamnavigator:
            if not open_desktop('hamnavigator'):
                raise RuntimeError(ui_language.t('Windows-radiorommet er ikke installert.'))
        else:
            widget() if args.widget else open_app()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), 'HamNavigator MY SHACK', 0x10)
        else:
            raise
