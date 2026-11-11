"""Link the GUI test to the same objects as Digital and decode a known off-air WAV."""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import urllib.request

here = Path(__file__).resolve().parent
build = Path("/tmp/hn-build")
src = Path("/tmp/hn-src/HamNavigator-kildekode/src")
recording = "https://raw.githubusercontent.com/kgoba/ft8_lib/9fec6ca39886edbf96f4f5e71edc76da5074e871/test/wav/websdr_test2.wav"
with tempfile.TemporaryDirectory() as folder:
    home = Path(folder)
    sample = home / "120000.wav"
    with urllib.request.urlopen(recording, timeout=30) as response:
        sample.write_bytes(response.read())
    if hashlib.sha256(sample.read_bytes()).hexdigest() != "9a9d7fb54241141242dbfcbca6df3ecf36a30a974e72651e885f8ccc08128170":
        raise ValueError("Unexpected recording checksum")
    recipe = subprocess.check_output(["make","-Bn"],cwd=build,text=True)
    commands = [shlex.split(line) for line in recipe.splitlines() if " -o " in line]
    compile_args = next(c for c in commands if c[-1].endswith("/src/main.cpp") and "-c" in c)
    primary = compile_args[compile_args.index("-o") + 1]
    test_obj = str(home / "wavcheck.o")
    compile_args[compile_args.index("-o") + 1] = test_obj
    compile_args[-1:] = [str(here / "wavcheck.cpp"), "-I" + str(src)]
    subprocess.run(compile_args,cwd=build,check=True)
    link_args = next(c for c in commands if primary in c and "bin/HamNavigator" in c and "-c" not in c)
    link_args[link_args.index(primary)] = test_obj
    executable = home / "wavcheck"
    link_args[link_args.index("-o") + 1] = str(executable)
    subprocess.run(link_args,cwd=build,check=True)
    os.environ.update(XDG_DATA_HOME=folder,HAMNAVIGATOR_LANGUAGE="en",QT_QPA_PLATFORM="offscreen",
                      PULSE_SERVER="unix:" + str(home / "no-pulse"))
    sys.path.insert(0, "/usr/lib/hamnavigator-portable")
    from pi_station import prepare
    prepare()
    subprocess.run([executable,sample],cwd=os.environ["HN_DIGITAL_HOME"],timeout=150,check=True)
