"""Local voice callsign assistance. No cloud inference or automatic logging."""
from __future__ import annotations
import ui_language
import base64
import collections
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import site
import subprocess
import sys
import threading
import time
import unicodedata
import wave

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / 'models' / 'whisper-small'
PHONETIC = {
    'ALFA':'A','ALPHA':'A','BRAVO':'B','CHARLIE':'C','DELTA':'D','ECHO':'E','EKKO':'E',
    'FOXTROT':'F','GOLF':'G','HOTEL':'H','INDIA':'I','JULIET':'J','JULIETT':'J','JULIETTE':'J',
    'KILO':'K','LIMA':'L','MIKE':'M','NOVEMBER':'N','OSCAR':'O','OSKAR':'O','PAPA':'P',
    'QUEBEC':'Q','ROMEO':'R','SIERRA':'S','TANGO':'T','UNIFORM':'U','VICTOR':'V','VIKTOR':'V',
    'WHISKEY':'W','WHISKY':'W','XRAY':'X','YANKEE':'Y','ZULU':'Z',
    'ZERO':'0','NULL':'0','ONE':'1','EN':'1','ETT':'1','TWO':'2','TO':'2','THREE':'3','TRE':'3',
    'FOUR':'4','FIRE':'4','FIVE':'5','FEM':'5','SIX':'6','SEKS':'6','SEVEN':'7','SJU':'7','SYV':'7',
    'EIGHT':'8','ATTE':'8','NINE':'9','NINER':'9','NI':'9','SLASH':'/','STROKE':'/',
    'PORTABLE':'/P','MOBILE':'/M',
}
CALL_RE = re.compile(r'(?=.{3,20}$)(?:[A-Z0-9]{1,4}/)?(?=[A-Z0-9]*[A-Z])[A-Z0-9]{1,3}\d{1,4}[A-Z]{1,4}(?:/(?:P|M|MM|AM|QRP|\d|[A-Z0-9]{1,4}))?')


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.upper()) if not unicodedata.combining(c))


def extract_callsigns(text):
    """Conservative spelling/format suggestions, never a claim of verification."""
    text = normalized(text)
    text = re.sub(r'\bX[ -]RAY\b', 'XRAY', text)
    text = re.sub(r'\bFOX[ -]TROT\b', 'FOXTROT', text)
    tokens = re.findall(r'[A-Z0-9/]+|[.!?;]', text)
    found = {}
    def add(call, evidence, kind):
        if CALL_RE.fullmatch(call) and call not in found:
            found[call] = {'call':call, 'evidence':evidence, 'kind':kind}
    for i, token in enumerate(tokens):
        if i and tokens[i-1] in ('GRID','LOCATOR','LOKATOR','LOKATORRUTE'):
            continue
        if any(c.isdigit() for c in token):
            add(token, token, 'tekst')
    run, words = [], []
    def flush():
        if run:
            call = ''.join(run)
            # Repeated uninterrupted spelling should not create a longer callsign.
            if len(run)%2 == 0 and run[:len(run)//2] == run[len(run)//2:]:
                call = ''.join(run[:len(run)//2])
            if len(words) >= 3:
                add(call, ' '.join(words), 'fonetisk')
        run.clear(); words.clear()
    for token in tokens:
        value = PHONETIC.get(token)
        if value is None and re.fullmatch(r'[A-Z]|\d{1,4}|/', token):
            value = token
        if value is None:
            flush()
        else:
            run.append(value); words.append(token)
    flush()
    return list(found.values())[:6]


def load_dependencies():
    directory = ROOT / '.venv-audio' / 'Lib' / 'site-packages'
    if directory.is_dir():
        site.addsitedir(str(directory))
    os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
    # Runtime inference must use installed local assets, never upload audio.
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    import numpy as np
    import pyaudiowpatch as pa
    return np, pa


DEVICE_SCAN_LOCK = threading.Lock()
DEVICE_CACHE = None
DEVICE_CACHE_UNTIL = 0.0


def list_devices():
    """Keep PortAudio initialization out of the threaded web server process.

    PyAudioWPatch can access-violate when two requests initialize it together.
    A short-lived, serialized scanner also contains native driver failures.
    This only enumerates devices; it never opens an audio stream.
    """
    global DEVICE_CACHE, DEVICE_CACHE_UNTIL
    with DEVICE_SCAN_LOCK:
        if DEVICE_CACHE is not None and time.monotonic() < DEVICE_CACHE_UNTIL:
            return [dict(device) for device in DEVICE_CACHE]
        executable = Path(sys.executable)
        if executable.name.lower() == 'pythonw.exe':
            executable = executable.with_name('python.exe')
        try:
            scan = subprocess.run(
                [str(executable), '-E', '-s', str(Path(__file__).resolve()), '--list-devices'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=12, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise ValueError(ui_language.t('Windows svarte ikke på søket etter lydkilder. Prøv Oppdater lydkilder igjen.')) from exc
        if scan.returncode != 0:
            raise ValueError(ui_language.t('Kunne ikke hente lydkildene fra Windows. Loggbok og Cloud kjører fortsatt. Prøv Oppdater lydkilder igjen.'))
        try:
            devices = json.loads(scan.stdout.decode('utf-8'))
            if not isinstance(devices, list) or len(devices) > 2048:
                raise ValueError('Invalid device list')
            for device in devices:
                if not isinstance(device, dict) or not all(key in device for key in ('id','name','loopback','rate','channels')):
                    raise ValueError('Invalid device entry')
        except (ValueError, UnicodeError) as exc:
            raise ValueError(ui_language.t('Windows returnerte en ugyldig liste over lydkilder. Prøv igjen.')) from exc
        DEVICE_CACHE, DEVICE_CACHE_UNTIL = devices, time.monotonic() + 5
        return [dict(device) for device in devices]


def _scan_devices():
    _, pa = load_dependencies()
    result = []
    with pa.PyAudio() as host:
        for i in range(host.get_device_count()):
            d = host.get_device_info_by_index(i)
            if int(d['maxInputChannels']) < 1:
                continue
            api = host.get_host_api_info_by_index(d['hostApi'])
            # WASAPI gives ordinary inputs and PC-output loopback without duplicates.
            if api['type'] != pa.paWASAPI:
                continue
            result.append({'id':int(d['index']), 'name':d['name'], 'loopback':bool(d.get('isLoopbackDevice')), 'rate':int(d['defaultSampleRate']), 'channels':int(d['maxInputChannels'])})
        if not result:
            for i in range(host.get_device_count()):
                d = host.get_device_info_by_index(i)
                if int(d['maxInputChannels']) > 0:
                    result.append({'id':i,'name':d['name'],'loopback':False,'rate':int(d['defaultSampleRate']),'channels':int(d['maxInputChannels'])})
    return result


def prepare_samples(samples, rate, radio_filter=True):
    np, _ = load_dependencies()
    from scipy.signal import butter, sosfilt, resample_poly
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    samples = np.nan_to_num(samples)
    if rate != 16000:
        gcd = math.gcd(int(rate),16000)
        samples = resample_poly(samples,16000//gcd,int(rate)//gcd).astype(np.float32)
    if radio_filter and len(samples):
        samples = sosfilt(butter(4,[220,3400],btype='bandpass',fs=16000,output='sos'), samples).astype(np.float32)
    peak = float(np.max(np.abs(samples))) if len(samples) else 0
    if peak > .001:
        samples *= min(3.0, .8/peak)
    return np.clip(samples,-1,1).astype(np.float32)


def wav_bytes(samples):
    np, _ = load_dependencies()
    out = io.BytesIO()
    with wave.open(out,'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
    return out.getvalue()


class CallsignListener:
    def __init__(self):
        self.lock = threading.RLock()
        self.control_lock = threading.Lock()
        self.model_lock = threading.Lock()
        self.model = None
        self.capture_thread = None
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.jobs = queue.Queue(maxsize=2)
        self.results = collections.deque(maxlen=30)
        self.clips = {}
        self.state = {'running':False,'processing':False,'message':ui_language.t('Klar når du velger lydkilde'),'level_db':-90.0,'peak_db':-90.0,'dropped':0,'device':'','last_audio':None,'error':'','session':None,'heartbeat':0}

    def snapshot(self):
        with self.lock:
            return {**self.state, 'results':list(self.results), 'model_ready':(MODEL_PATH/'model.bin').is_file(), 'model_loaded':self.model is not None}

    def touch(self, session):
        with self.lock:
            if session != self.state['session']:
                raise ValueError(ui_language.t('Lytteøkten er ikke aktiv i dette vinduet.'))
            self.state['heartbeat'] = time.monotonic()
        return {'ok':True}

    def load_model(self):
        if self.model is None:
            load_dependencies()
            from faster_whisper import WhisperModel
            if not (MODEL_PATH/'model.bin').is_file():
                raise ValueError(ui_language.t('Talemodellen mangler. Kjør klargjøringen beskrevet i LES-MEG.'))
            self.model = WhisperModel(str(MODEL_PATH), device='cpu',compute_type='int8',cpu_threads=8,local_files_only=True)
        return self.model

    def transcribe(self, samples, language='en'):
        np, _ = load_dependencies()
        # Speech detection plus silence thresholds prevent most noise-only guesses.
        if len(samples) < 1600 or float(np.sqrt(np.mean(samples*samples))) < .0005:
            return ''
        with self.model_lock:
            model = self.load_model()
            segments, _ = model.transcribe(samples,language=None if language=='auto' else language,beam_size=5,temperature=0,condition_on_previous_text=False,vad_filter=True,vad_parameters={'min_silence_duration_ms':450,'speech_pad_ms':300},no_speech_threshold=.55,log_prob_threshold=-1.0,initial_prompt='Amateur radio voice communication. Callsigns are spelled using the NATO phonetic alphabet. Transcribe the spoken words and numbers. CQ, QRZ, over.')
            text = ' '.join(s.text.strip() for s in segments if s.no_speech_prob < .65 and s.avg_logprob > -1.2).strip()
        return text

    def add_result(self, samples, transcript, source, seconds, session):
        entry = {'id':secrets.token_hex(8),'time':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'text':transcript,'candidates':extract_callsigns(transcript),'source':source,'duration':round(seconds,1),'session':session}
        clip = wav_bytes(samples)
        with self.lock:
            self.results.appendleft(entry)
            self.clips[entry['id']] = clip
            retained = {r['id'] for r in self.results}
            self.clips = {k:v for k,v in self.clips.items() if k in retained}
        return entry

    def _work(self, stop, session, language, radio_filter):
        while not stop.is_set() or not self.jobs.empty():
            try:
                samples, rate, source = self.jobs.get(timeout=.3)
            except queue.Empty:
                continue
            try:
                with self.lock:
                    self.state['processing'] = True
                    self.state['message'] = ui_language.t('Tolker radiotale …')
                audio = prepare_samples(samples,rate,radio_filter)
                text = self.transcribe(audio,language)
                if text:
                    self.add_result(audio,text,source,len(samples)/rate,session)
                with self.lock:
                    self.state['message'] = ui_language.t('Lytter – venter på neste taleavsnitt') if not stop.is_set() else ui_language.t('Stoppet')
            except Exception as exc:
                with self.lock:
                    self.state['error'] = str(exc)
                    self.state['message'] = ui_language.t('Tolkingen stoppet. Kontroller lydkilde og oppsett.')
                stop.set()
            finally:
                with self.lock:
                    self.state['processing'] = False
                self.jobs.task_done()

    def _enqueue(self, samples, rate, source):
        try:
            self.jobs.put_nowait((samples,rate,source))
        except queue.Full:
            with self.lock:
                self.state['dropped'] += 1

    def _capture(self, stop, session, config):
        np, pa = load_dependencies()
        try:
            with self.model_lock:
                self.load_model()
            if stop.is_set():
                return
            self.worker_thread = threading.Thread(target=self._work,args=(stop,session,config['language'],config['filter']),daemon=True)
            self.worker_thread.start()
            with pa.PyAudio() as host:
                d = host.get_device_info_by_index(config['device'])
                if d['name'] != config['device_name']:
                    raise ValueError(ui_language.t('Lydkilden har endret seg. Oppdater listen og velg den på nytt.'))
                rate = int(d['defaultSampleRate'])
                channels = min(2,int(d['maxInputChannels']))
                block = max(512,int(rate*.1))
                incoming = queue.Queue(maxsize=60)
                def receive(raw, frame_count, timing, status):
                    if stop.is_set():
                        return (None,pa.paComplete)
                    try:
                        incoming.put_nowait(raw)
                    except queue.Full:
                        with self.lock:self.state['dropped'] += 1
                    return (None,pa.paContinue)
                stream = host.open(format=pa.paInt16,channels=channels,rate=rate,input=True,input_device_index=config['device'],frames_per_buffer=block,stream_callback=receive)
                frames, quiet, total = [], 0.0, 0.0
                with self.lock:
                    self.state['message'] = ui_language.t('Lytter – si eller motta et kallesignal')
                try:
                    while not stop.is_set():
                        if time.monotonic()-self.state['heartbeat'] > 15:
                            with self.lock:
                                self.state['message'] = ui_language.t('Stoppet fordi lyttevinduet ble lukket eller mistet forbindelsen')
                            stop.set(); break
                        try:
                            raw = incoming.get(timeout=.2)
                        except queue.Empty:
                            if not stream.is_active():
                                raise ValueError(ui_language.t('Lydstrømmen ble avsluttet. Kontroller lydkilden og start igjen.'))
                            continue
                        mono = np.frombuffer(raw,dtype='<i2').astype(np.float32).reshape(-1,channels).mean(axis=1)/32768
                        rms = float(np.sqrt(np.mean(mono*mono)))
                        peak = float(np.max(np.abs(mono)))
                        db = max(-90,20*math.log10(max(rms,1e-9)))
                        with self.lock:
                            self.state['level_db'] = round(db,1)
                            self.state['peak_db'] = round(max(-90,20*math.log10(max(peak,1e-9))),1)
                            self.state['last_audio'] = time.time()
                        duration = len(mono)/rate
                        # Keep continuous radio noise bounded; inference VAD filters non-speech.
                        if db >= config['gate'] or frames:
                            frames.append(mono);total += duration
                            quiet = quiet+duration if db < config['gate'] else 0
                            if total >= 12 or (quiet >= .9 and total >= 2):
                                audio = np.concatenate(frames)
                                self._enqueue(audio,rate,d['name'])
                                if total >= 12:
                                    # Two seconds of overlap reduce split callsigns at chunk edges.
                                    frames=[audio[-rate*2:]]; total=2.0
                                else:
                                    frames=[];total=0
                                quiet=0
                    if frames and total >= 1.5:
                        self._enqueue(np.concatenate(frames),rate,d['name'])
                finally:
                    stream.stop_stream();stream.close()
        except Exception as exc:
            with self.lock:
                self.state['error'] = str(exc)
                self.state['message'] = ui_language.t('Kunne ikke lytte. Velg en tilgjengelig lydinngang.')
        finally:
            stop.set()
            with self.lock:
                self.state['running'] = False
                self.state['level_db'] = -90
                if not self.state['error'] and not self.state['message'].startswith(ui_language.t('Stoppet fordi')):
                    self.state['message'] = ui_language.t('Fullfører siste lydavsnitt …') if self.state['processing'] else ui_language.t('Stoppet')

    def start(self, config):
        with self.control_lock:
            if self.capture_thread and self.capture_thread.is_alive() or self.worker_thread and self.worker_thread.is_alive():
                raise ValueError(ui_language.t('Lytteren er allerede i gang eller fullfører siste avsnitt.'))
            if self.state['processing']:
                raise ValueError(ui_language.t('Vent til lydfilen er ferdig tolket.'))
            try:
                device_id = int(config.get('device'))
                gate = float(config.get('gate',-48))
            except (TypeError,ValueError):
                raise ValueError(ui_language.t('Velg lydkilde og gyldig lydgrense.'))
            if not math.isfinite(gate) or not -75 <= gate <= -15:
                raise ValueError(ui_language.t('Lydgrensen må være mellom −75 og −15 dBFS.'))
            language = config.get('language','en')
            if language not in ('en','no','auto'):
                raise ValueError(ui_language.t('Velg engelsk, norsk eller automatisk språk.'))
            device = next((d for d in list_devices() if d['id']==device_id),None)
            if not device:
                raise ValueError(ui_language.t('Lydkilden finnes ikke. Oppdater listen.'))
            if config.get('device_name') != device['name']:
                raise ValueError(ui_language.t('Lydkilden har endret seg. Velg den på nytt.'))
            self.stop_event = threading.Event()
            self.jobs = queue.Queue(maxsize=2)
            session = secrets.token_hex(8)
            with self.lock:
                self.state.update(running=True,error='',message=ui_language.t('Klargjør lokal talegjenkjenning …'),session=session,device=device['name'],dropped=0,heartbeat=time.monotonic())
            settings = {'device':device_id,'device_name':device['name'],'language':language,'gate':gate,'filter':bool(config.get('filter',True))}
            self.capture_thread=threading.Thread(target=self._capture,args=(self.stop_event,session,settings),daemon=True)
            self.capture_thread.start()
        return {'ok':True,'session':session}

    def stop(self):
        self.stop_event.set()
        with self.lock:
            self.state['message']=ui_language.t('Stopper lydinngangen …') if self.state['running'] else self.state['message']
        return {'ok':True}

    def analyze_file(self, encoded, language='en', radio_filter=True):
        if language not in ('en','no','auto'):
            raise ValueError(ui_language.t('Ugyldig språk.'))
        raw = base64.b64decode(encoded,validate=True)
        if len(raw) > 12_000_000:
            raise ValueError(ui_language.t('Bruk en lydfil under 12 MB og maks 60 sekunder.'))
        np, _ = load_dependencies()
        with wave.open(io.BytesIO(raw),'rb') as wav:
            if wav.getsampwidth()!=2 or wav.getnchannels() not in (1,2) or wav.getcomptype()!='NONE':
                raise ValueError(ui_language.t('Bruk WAV med 16-bit PCM, mono eller stereo.'))
            rate, channels, frames = wav.getframerate(),wav.getnchannels(),wav.getnframes()
            if not 8000<=rate<=192000 or frames/rate>60 or frames/rate<.5:
                raise ValueError(ui_language.t('Bruk et WAV-klipp på 0,5–60 sekunder, 8–192 kHz.'))
            payload=wav.readframes(frames)
            if len(payload)!=frames*channels*2:
                raise ValueError(ui_language.t('WAV-filen er avkortet.'))
            samples=np.frombuffer(payload,dtype='<i2').astype(np.float32).reshape(-1,channels).mean(axis=1)/32768
        with self.control_lock:
            if self.state['running'] or self.state['processing'] or self.worker_thread and self.worker_thread.is_alive():
                raise ValueError(ui_language.t('Stopp lyttingen og vent til tolkingen er ferdig før du åpner en lydfil.'))
            with self.lock:
                self.state.update(processing=True,error='',message=ui_language.t('Tolker WAV-filen …'))
        def work():
            try:
                audio=prepare_samples(samples,rate,radio_filter)
                text=self.transcribe(audio,language)
                self.add_result(audio,text or ui_language.t('Ingen tydelig tale funnet.'),'WAV-fil',frames/rate,secrets.token_hex(8))
                with self.lock:self.state['message']=ui_language.t('Lydfilen er ferdig tolket')
            except Exception as exc:
                with self.lock:self.state.update(error=str(exc),message=ui_language.t('Kunne ikke tolke lydfilen'))
            finally:
                with self.lock:self.state['processing']=False
        threading.Thread(target=work,daemon=True).start()
        return {'ok':True}

    def clear(self):
        with self.lock:
            if self.state['running'] or self.state['processing'] or self.worker_thread and self.worker_thread.is_alive():
                raise ValueError(ui_language.t('Stopp lytteren og vent til tolkingen er ferdig først.'))
            self.results.clear();self.clips.clear()
        return {'ok':True}

    def clip(self, key):
        with self.lock:
            if key not in self.clips:
                raise ValueError(ui_language.t('Lydavsnittet er ikke lenger i minnet.'))
            return self.clips[key]


if __name__ == '__main__' and sys.argv[1:] == ['--list-devices']:
    sys.stdout.buffer.write(json.dumps(_scan_devices(), ensure_ascii=True).encode('utf-8'))
