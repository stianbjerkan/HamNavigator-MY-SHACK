"""Run on the installed ARM64 package in a throwaway desktop session. No RF or Cloud writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

APP = Path("/usr/lib/hamnavigator-portable")
sys.path.insert(0, str(APP))

with tempfile.TemporaryDirectory() as folder:
    os.environ.update(XDG_DATA_HOME=folder, QT_QPA_PLATFORM="offscreen")
    from pi_station import prepare, protect
    data = prepare()
    import radio_assistant as radio
    from shared_log import SharedLog
    log = SharedLog(data)
    row = {"CALL":"K1ABC","QSO_DATE":"20260105","TIME_ON":"145200","FREQ":"14.074","MODE":"FT8"}
    log.commit([], [row])
    assert log.path == data / "log/hamnavigator.adi"
    assert prepare() == data and len(log.read()) == 1
    for code in ("nb", "en", "sv"):
        subprocess.run([APP / "HamNavigator", "--language-selftest"],
                       env={**os.environ, "HAMNAVIGATOR_LANGUAGE": code}, check=True, timeout=20)
    native_root = Path(folder) / "native"
    (native_root / "release/HamNavigator/log").mkdir(parents=True)
    subprocess.run([APP / "HamNavigator","--shared-log-selftest"],
                   env={**os.environ, "HN_SHARED_TEST_ROOT": str(native_root)}, check=True, timeout=60)
    assert len(log.read()) == 1 and log.read()[0]["CALL"] == "K1ABC"
    dummy = "generated-test-secret"
    sealed = protect(dummy)
    assert dummy not in sealed and protect(sealed, True) == dummy
    bridge = subprocess.Popen([sys.executable, APP / "radio_assistant.py", "--server"])
    try:
        for _ in range(80):
            if radio.healthy():
                break
            if bridge.poll() is not None:
                raise RuntimeError("Web client failed to start")
            time.sleep(.1)
        assert radio.healthy()
        with urllib.request.urlopen(radio.URL + "/api/state", timeout=4) as response:
            assert json.load(response)["login_required"]
        with urllib.request.urlopen(radio.URL + "/",timeout=4) as response:
            assert "DE-19" in response.read().decode()
        for code in ("en", "sv"):
            assert "DE-19" in (APP / "languages" / code / "app.html").read_text()
        print("PASS ARM64 native help (three languages), Digital ADIF update, keyring encryption, account gate, USB guides")
    finally:
        bridge.terminate()
        bridge.wait(timeout=10)
