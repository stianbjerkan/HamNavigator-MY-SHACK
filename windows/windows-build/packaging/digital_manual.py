"""Rebuild only Digital's embedded documentation using the verified build cache."""
from pathlib import Path
import os,shutil,subprocess,zipfile
from manuals import generate

SERVER=Path(__file__).resolve().parents[2]
TOOLS=Path('C:/Users/bjerk/Documents/ChatGPT/UTC time')
CACHE=TOOLS/'digital-source/MSHV_2766'
DEST=SERVER/'bygg/digital-manual'
source=TOOLS/'release/HamNavigator-Samlet/release/HamNavigator/HamNavigator-kildekode.zip'
with zipfile.ZipFile(source) as z:
    for n in z.namelist():
        if n.endswith(('.cpp','.h','.pro','.qrc')) and '/windows-identity/' not in n:
            p=CACHE/Path(n).relative_to('HamNavigator-kildekode')
            assert p.is_file() and p.read_bytes()==z.read(n),'Cache source mismatch: '+n
shutil.copytree(CACHE,DEST,dirs_exist_ok=True,ignore=shutil.ignore_patterns('bin','.git'))
shutil.copytree(Path(__file__).resolve().parent/'digital-languages',DEST,dirs_exist_ok=True)
shutil.copy2(generate()/'HamNavigator-Digital-Qt.html',DEST/'src/hamnavigator-help.html')
shutil.copy2(generate()/'HamNavigator-Digital-Qt.en.html',DEST/'src/hamnavigator-help-en.html')
shutil.copy2(generate()/'HamNavigator-Digital-Qt.sv.html',DEST/'src/hamnavigator-help-sv.html')
qt=TOOLS/'.toolchains/Qt/5.15.2/mingw81_64/bin'
mingw=TOOLS/'.toolchains/Qt/Tools/mingw810_64/bin'
env={**os.environ,'PATH':str(mingw)+os.pathsep+str(qt)+os.pathsep+os.environ['PATH']}
subprocess.run([str(qt/'lrelease.exe'),str(DEST/'src/HvTranslations/mshv_svse.ts'),'-qm',str(DEST/'src/HvTranslations/mshv_svse.qm')],env=env,check=True)
subprocess.run([str(qt/'qmake.exe'),'RadioassistentDigital.pro','-spec','win32-g++'],cwd=DEST,env=env,check=True)
subprocess.run([str(mingw/'mingw32-make.exe'),'-f','Makefile.Release','-j4'],cwd=DEST,env=env,check=True)
print('Digital rebuilt with current embedded handbook:',DEST/'bin/HamNavigator.exe')
