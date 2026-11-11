"""Pi desktop entry, Digital process and secrets for the native Linux client."""
import base64
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
SEED = Path("/usr/share/hamnavigator-portable/station")
DIGITAL = ROOT / "HamNavigator"
_process = None
_process_lock = threading.Lock()


def station_paths():
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    data = base / "hamnavigator-portable"
    digital = data / "digital"
    os.environ.update(RADIOASSISTENT_DATA=str(data), HN_DIGITAL_HOME=str(digital))
    return data, digital


def prepare():
    os.umask(0o077)
    data, digital = station_paths()
    data.mkdir(parents=True, exist_ok=True)
    for name in ("settings", "settings/database", "log", "RxWavs", "Screenshots", "AllTxt"):
        (digital / name).mkdir(parents=True, exist_ok=True)
    # Seed packaged station resources once, preserving user edits and logs.
    with (data / ".init.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for source in sorted(SEED.rglob("*")):
            if source.is_file():
                target = digital / source.relative_to(SEED)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = target.with_suffix(target.suffix + ".new")
                    shutil.copyfile(source, temp)
                    os.replace(temp, target)
        from shared_log import SharedLog
        SharedLog(data).initialize()
    return data


def protect(text, decrypt=False):
    """Wrap tokens, sync caches and vault data with the desktop login keyring."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from keyring.backends.SecretService import Keyring
    data = Path(os.environ["RADIOASSISTENT_DATA"])
    with (data / ".keyring.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ring = Keyring()
        service, account = "HamNavigator Portable", "local-data-key-v1"
        encoded = ring.get_password(service, account)
        if encoded is None:
            if decrypt:
                raise ValueError("HamNavigator: unlock or restore the desktop login keyring.")
            encoded = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()
            ring.set_password(service, account, encoded)
    cipher = AESGCM(base64.b64decode(encoded, validate=True))
    aad = b"HamNavigator Portable v1"
    if decrypt:
        blob = base64.b64decode(text, validate=True)
        return cipher.decrypt(blob[:12], blob[12:], aad).decode()
    nonce = os.urandom(12)
    return base64.b64encode(nonce + cipher.encrypt(nonce, text.encode(), aad)).decode()


def open_panel(panel):
    global _process
    if panel not in ("digital", "mshv", "hamnavigator"):
        return False
    data, digital = station_paths()
    with _process_lock:
        if _process is None or _process.poll() is not None:
            with (data / "digital.log").open("ab") as log:
                _process = subprocess.Popen([str(DIGITAL)], cwd=digital, stdout=log, stderr=log)
    return True


def main():
    data = prepare()
    import radio_assistant as app
    with (data / ".backend.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not app.healthy():
            if app.backend_info() is not None:
                raise RuntimeError("The local HamNavigator port is in use.")
            with (data / "startup.log").open("ab") as log:
                worker = subprocess.Popen([sys.executable, str(ROOT / "radio_assistant.py"), "--server"],
                                          cwd=data, stdout=log, stderr=log, start_new_session=True)
            for _ in range(75):
                if app.healthy():
                    break
                if worker.poll() is not None:
                    raise RuntimeError(f"HamNavigator could not start. See {data / 'startup.log'}")
                time.sleep(0.15)
            else:
                raise RuntimeError(f"HamNavigator did not respond. See {data / 'startup.log'}")
    if not webbrowser.open(app.URL + "/#ft8"):
        raise RuntimeError("Open " + app.URL + " in the desktop browser.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import tkinter.messagebox
        tkinter.messagebox.showerror("HamNavigator Portable", str(error))
        raise SystemExit(1)
