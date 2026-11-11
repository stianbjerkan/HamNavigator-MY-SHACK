"""Create the ARM64 Debian client from the linked Digital binary and public sources."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from client_port import adapt

here = Path(__file__).resolve().parent
client = here.parent / "windows"
version = (client / "VERSION").read_text().strip() + "-1"
binary = Path(sys.argv[1])
header = binary.read_bytes()[:20]
if header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != 183:
    raise SystemExit("Expected a little-endian ARM64 ELF executable.")

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    app = root / "usr/lib/hamnavigator-portable"
    app.mkdir(parents=True)
    for path in client.iterdir():
        if path.is_file() and path.suffix in (".py", ".js", ".html", ".css", ".json"):
            if not path.name.startswith("test_") and path.name not in (
                "desktop_host.py", "update_dialog.py", "native_windows.py", "app_update.py"):
                shutil.copyfile(path, app / path.name)
    for folder in ("map-data", "manuals", "languages", "vendor"):
        shutil.copytree(client / folder, app / folder)
    shutil.copyfile(client / "VERSION", app / "VERSION")
    shutil.copyfile(here / "pi_station.py", app / "pi_station.py")
    adapt(app)
    shutil.copy2(binary, app / "HamNavigator")
    subprocess.run(["strip", str(app / "HamNavigator")], check=True)
    shutil.copytree(here / "station", root / "usr/share/hamnavigator-portable/station")
    docs = root / "usr/share/doc/hamnavigator-portable"
    docs.mkdir(parents=True)
    for path in here.glob("guide-*.html"):
        shutil.copyfile(path, docs / path.name)
    for name in ("COPYING.txt","OPPHAV.txt","license.txt"):
        shutil.copyfile(Path("/tmp/hn-src/HamNavigator-kildekode") / name, docs / name)
    shutil.copyfile(here / "README.md", docs / "README.md")
    (docs / "copyright").write_text((docs / "OPPHAV.txt").read_text() +
        "\nSee COPYING.txt and license.txt. The public source and build instructions are linked in README.md.\n")
    script = root / "usr/bin/hamnavigator-portable"
    script.parent.mkdir(parents=True)
    script.write_text('#!/bin/sh\nexec /usr/bin/python3 -E -s /usr/lib/hamnavigator-portable/pi_station.py "$@"\n')
    script.chmod(0o755)
    menu = root / "usr/share/applications/hamnavigator-portable.desktop"
    menu.parent.mkdir(parents=True)
    menu.write_text("[Desktop Entry]\nType=Application\nName=HamNavigator Portable\n"
                    "Exec=hamnavigator-portable\nIcon=hamnavigator-portable\nTerminal=false\nCategories=Network;HamRadio;\n")
    icon = root / "usr/share/pixmaps/hamnavigator-portable.png"
    icon.parent.mkdir(parents=True)
    shutil.copyfile("/tmp/hn-src/HamNavigator-kildekode/src/pic/hamnavigator.png", icon)
    control = root / "DEBIAN/control"
    control.parent.mkdir()
    control.write_text(f"Package: hamnavigator-portable\nVersion: {version}\nArchitecture: arm64\n"
        "Maintainer: LB7YK RadioLab <post@lb7yk.no>\nSection: hamradio\nPriority: optional\n"
        "Depends: python3 (>= 3.11), python3-cryptography, python3-keyring, gnome-keyring, python3-tk, "
        "libqt5widgets5, libqt5websockets5, libqt5network5, libfftw3-double3, libasound2, libpulse0, "
        "libstdc++6, alsa-utils, xdg-utils, ca-certificates\n"
        "Description: HamNavigator portable digital amateur-radio station for Raspberry Pi\n"
        " Native Digital station with USB audio, CAT/PTT, ADIF log and Cloud client.\n")
    out = here / "dist"
    out.mkdir(exist_ok=True)
    package = out / f"hamnavigator-portable_{version}_arm64.deb"
    subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(package)], check=True)
