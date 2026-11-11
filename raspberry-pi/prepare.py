"""Apply the Raspberry Pi adaptations to the hash-pinned Digital release source."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
here = Path(__file__).resolve().parent


def replace(name, old, new):
    path = root / name
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if text.count(old) != 1:
        raise ValueError(f"Unexpected source in {name}: {old}")
    path.write_text(text.replace(old, new), encoding="utf-8", errors="surrogateescape")


# Debian supplies the shared FFTW library built for its own ABI.
project = (root / "MSHV_Slarm64_PI.pro").read_text(encoding="utf-8", errors="surrogateescape")
project = project.replace("src/Hv_Lib_fftw/lin_arm/libfftw3_slarm64_pi.a", "-lfftw3")
project += "\nTARGET = HamNavigator\nRESOURCES += src/hamnavigator.qrc\n"
(root / "HamNavigatorPi.pro").write_text(project, encoding="utf-8", errors="surrogateescape")

# Use the station's writable per-user directory for logs, settings and recordings.
for name in ("main.cpp", "main_ms.cpp", "HvDecodeList/decodelist.cpp",
             "HvDecodeList/hvcty.cpp", "HvTxW/HvAstroDataW/hvastrodataw.cpp"):
    path = root / "src" / name
    code = path.read_text(encoding="utf-8", errors="surrogateescape")
    code = code.replace("QCoreApplication::applicationDirPath()",
                        'qEnvironmentVariable("HN_DIGITAL_HOME", QCoreApplication::applicationDirPath())')
    path.write_text(code, encoding="utf-8", errors="surrogateescape")

replace("src/HvTxW/HvLogW/hvlogw.cpp",
        'root+"/runtime/python.exe",QStringList()<<"-E"<<"-s"<<(root+"/shared_log.py")',
        '"/usr/bin/python3",QStringList()<<"-E"<<"-s"<<"/usr/lib/hamnavigator-portable/shared_log.py"')
replace("src/HvTxW/HvLogW/hvlogw.cpp", 'QString root=QDir(AppPath+"/../..").absolutePath();',
        '// The packaged shared-log bridge is read-only and station independent.')

# QextSerialPort accepts names relative to /dev. Preserve manual tty names,
# including names saved before the adapter acquired a persistent udev alias.
replace("src/HvRigControl/hvrigcontrol.cpp", '#include "qexsp_1_2rc/qextserialenumerator.h"',
        '#include "qexsp_1_2rc/qextserialenumerator.h"\n#include <QDir>\n#include <QFileInfo>')
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

# A synchronous connection failure may occur before the original state callback
# was registered. Bound discovery even if a Pulse/PipeWire service accepts a
# connection and stops responding. The caller continues with ALSA USB devices.
audio = root / "src/SettingsMs/settings_ms.cpp"
code = audio.read_text(encoding="utf-8", errors="surrogateescape")
start = code.index("int _pa_get_devicelist_(")
end = code.index("\n#endif", start)
code = code[:start] + (here / "pulse_discovery.inc").read_text(encoding="utf-8") + code[end:]
code = code.replace("#include <pulse/pulseaudio.h>", "#include <pulse/pulseaudio.h>\n#include <QElapsedTimer>\n#include <QThread>")
code = code.replace("if (eol > 0)", "if (eol != 0 || !l || !l->name)")
code = code.replace("strncpy(pa_devicelist[ctr].description, l->description, 255);",
                    "strncpy(pa_devicelist[ctr].description, l->description ? l->description : l->name, 255);")
audio.write_text(code, encoding="utf-8", errors="surrogateescape")

# Field stations start in FT8 on a new profile; saved mode selections take precedence.
replace("src/main_ms.cpp", "rb_mode[2]->setChecked(true);//1.26 HV important set to default mode fsk441",
        "rb_mode[11]->setChecked(true);// FT8 on the first Pi launch")
help_file = root / "src/HvHelpMs/hvhelpms.cpp"
help_code = help_file.read_text(encoding="utf-8", errors="surrogateescape")
start = help_code.index("//url_hv = new QUrl();")
end = help_code.index('text_browser->setSource(QUrl(hnLanguage()', start)
help_file.write_text(help_code[:start] + help_code[end:], encoding="utf-8", errors="surrogateescape")
replace("src/SettingsMs/settings_ms.cpp", '#include "settings_ms.h"',
        '#include "settings_ms.h"\n#include "../hn_language.h"')
replace("src/SettingsMs/settings_ms.cpp",
        r'"No sound device detected\n"' + '\n                              ' +
        r'"Close application and install\nsoundcard driver please."',
        'hnLanguage()=="sv" ? QString::fromUtf8("Anslut DE-19 eller Digirig via USB och öppna Digital igen för att visa ljudenheterna.") : '
        'hnText("Koble til DE-19 eller Digirig via USB og åpne Digital på nytt for å vise lydenhetene.", '
        '"Connect the DE-19 or Digirig via USB, then reopen Digital to refresh the audio devices.")')
