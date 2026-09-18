"""Package the corresponding Digital/Map sources and the Windows resource step."""
from pathlib import Path
import shutil
import zipfile
import re
from app_identity import refresh_checksums

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent.parent
BUNDLE = SERVER / 'bygg/klient'
OUT = SERVER / 'bygg/branding-sources'
EXTRAS = ('app_identity.py', 'hamnavigator.ico', 'IDENTITET.txt')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    digital_source = BUNDLE / 'release/HamNavigator/HamNavigator-kildekode.zip'
    digital_output = OUT / 'HamNavigator-Digital-kildekode.zip'
    with zipfile.ZipFile(digital_source) as source, zipfile.ZipFile(digital_output, 'w', zipfile.ZIP_DEFLATED) as target:
        written=set()
        overlay=HERE/'digital-languages'
        for info in source.infolist():
            if '/windows-identity/' not in info.filename:
                relative=Path(info.filename).relative_to('HamNavigator-kildekode')
                if (overlay/relative).is_file():
                    target.writestr(info,(overlay/relative).read_bytes())
                elif info.filename.endswith('/src/hamnavigator-help.html') or re.search(r'resources/url_help/(en|ru)/help_(en|ru)\.html$',info.filename):
                    english=info.filename.endswith('/en/help_en.html')
                    target.writestr(info,(BUNDLE/'manuals'/('HamNavigator-Digital-Qt.en.html' if english else 'HamNavigator-Digital-Qt.html')).read_bytes())
                elif info.filename.endswith('/src/hamnavigator-help-en.html'):
                    target.writestr(info,(BUNDLE/'manuals/HamNavigator-Digital-Qt.en.html').read_bytes())
                else:
                    target.writestr(info, source.read(info))
                written.add(info.filename)
        for path in sorted(overlay.rglob('*')):
            if path.is_file():
                name='HamNavigator-kildekode/'+path.relative_to(overlay).as_posix()
                if name not in written:target.write(path,name);written.add(name)
        for code in ('en','sv'):
            name='HamNavigator-kildekode/src/hamnavigator-help-'+code+'.html'
            if name not in written:target.write(BUNDLE/('manuals/HamNavigator-Digital-Qt.'+code+'.html'),name)
        name='HamNavigator-kildekode/src/HvTranslations/mshv_svse.qm'
        if name not in written:target.write(SERVER/'bygg/digital-manual/src/HvTranslations/mshv_svse.qm',name)
        for name in EXTRAS:
            target.write(HERE / name, 'HamNavigator-kildekode/windows-identity/' + name)
    shutil.copy2(digital_output, digital_source)
    app = BUNDLE / 'release/HamNavigator-Map/resources/app'
    with zipfile.ZipFile(OUT / 'HamNavigator-Map-kildekode.zip', 'w', zipfile.ZIP_DEFLATED) as target:
        for path in sorted(app.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                target.write(path, 'HamNavigator-Map/' + path.relative_to(app).as_posix())
        for name in EXTRAS:
            target.write(HERE / name, 'HamNavigator-Map/windows-identity/' + name)
    refresh_checksums(BUNDLE)
    print('Corresponding component sources packaged, with original notices and resource build instructions.')


if __name__ == '__main__':
    main()
