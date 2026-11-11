"""Apply the Raspberry Pi adaptations to the hash-pinned Digital release source."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
here = Path(__file__).resolve().parent


def replace(name, old, new):
    path = root / name
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise ValueError(f"Unexpected source in {name}: {old}")
    path.write_text(text.replace(old, new), encoding="utf-8")


# Debian supplies the shared FFTW library built for its own ABI.
project = (root / "MSHV_Slarm64_PI.pro").read_text(encoding="utf-8")
project = project.replace("src/Hv_Lib_fftw/lin_arm/libfftw3_slarm64_pi.a", "-lfftw3")
project += "\nTARGET = HamNavigator\nRESOURCES += src/hamnavigator.qrc\n"
(root / "HamNavigatorPi.pro").write_text(project, encoding="utf-8")

# Use the station's writable per-user directory for logs, settings and recordings.
for name in ("main.cpp", "main_ms.cpp", "HvDecodeList/decodelist.cpp",
             "HvDecodeList/hvcty.cpp", "HvTxW/HvAstroDataW/hvastrodataw.cpp"):
    path = root / "src" / name
    code = path.read_text(encoding="utf-8")
    code = code.replace("QCoreApplication::applicationDirPath()",
                        'qEnvironmentVariable("HN_DIGITAL_HOME", QCoreApplication::applicationDirPath())')
    path.write_text(code, encoding="utf-8")

replace("src/HvTxW/HvLogW/hvlogw.cpp",
        'root+"/runtime/python.exe",QStringList()<<"-E"<<"-s"<<(root+"/shared_log.py")',
        '"/usr/bin/python3",QStringList()<<"-E"<<"-s"<<"/usr/lib/hamnavigator-portable/shared_log.py"')
replace("src/HvTxW/HvLogW/hvlogw.cpp", 'QString root=QDir(AppPath+"/../..").absolutePath();',
        '// The packaged shared-log bridge is read-only and station independent.')

# QextSerialPort accepts names relative to /dev. Preserve manual tty names,
# including names saved before the adapter acquired a persistent udev alias.
replace("src/HvRigControl/hvrigcontrol.cpp", "    cb_port->addItems(lst_ports);", """
    for (const QString &directory : {QString("serial/by-id"), QString("serial/by-path")}) {
        QDir aliases("/dev/" + directory);
        QStringList paths;
        for (const QString &name : aliases.entryList(QDir::Files | QDir::System | QDir::NoDotAndDotDot, QDir::Name)) {
            QFileInfo link(aliases.filePath(name));
            if (link.isSymLink() && link.exists()) paths.append(directory + "/" + name);
        }
        lst_ports.append(paths);
    }
    cb_port->addItems(lst_ports);""")
