"""Install language controls while retaining native Map translations and stable handlers."""
from pathlib import Path
import shutil,json
HERE=Path(__file__).resolve().parent
def install(bundle):
    renderer=Path(bundle)/'release/HamNavigator-Map/resources/app/src/renderer'
    script=(HERE/'map_language.js').read_text(encoding='utf-8')
    dictionary=json.loads((HERE/'map-language-sv.json').read_text(encoding='utf-8'))
    assert '/* HN_SWEDISH_CATALOG */{}' in script
    (renderer/'lib/hamnavigator-language.js').write_text(script.replace('/* HN_SWEDISH_CATALOG */{}',json.dumps(dictionary,ensure_ascii=False)),encoding='utf-8')
    shutil.copy2(HERE/'map-i18n-sv.json',renderer.parents[1]/'resources/i18n/sv.json')
    p=renderer/'lib/gt.js';s=p.read_text(encoding='utf-8')
    if 'sv: "i18n/sv.json"' not in s:s=s.replace('GT.languages = {','GT.languages = {\n  sv: "i18n/sv.json",',1)
    p.write_text(s,encoding='utf-8')
    for p in [renderer/'GridTracker2.html',*renderer.glob('gt_*.html')]:
        s=p.read_text(encoding='utf-8')
        if 'lib/hamnavigator-language.js' not in s:
            assert '<head>' in s
            p.write_text(s.replace('<head>','<head>\n<script src="./lib/hamnavigator-language.js"></script>',1),encoding='utf-8')
    p=renderer/'lib/i18n.js';s=p.read_text(encoding='utf-8')
    if 'if(window.hnEnglish)locale=' not in s and 'if(["en","sv"].includes(window.hnLanguage))' not in s:
        s=s.replace('function readLocaleFile(locale)\n{','function readLocaleFile(locale)\n{\n  if(window.hnEnglish)locale="en";')
        p.write_text(s,encoding='utf-8')
    s=p.read_text(encoding='utf-8').replace('if(window.hnEnglish)locale="en";','if(["en","sv"].includes(window.hnLanguage))locale=window.hnLanguage;')
    p.write_text(s,encoding='utf-8')
    for name in ('hamnavigator-ui.js','hamnavigator-menus.js'):
        p=renderer/'lib'/name;s=p.read_text(encoding='utf-8')
        s=s.replace('text.textContent=label;','text.textContent=window.hnText(label);')
        s=s.replace("b.textContent='‹ Tilbake';","b.textContent=window.hnText('‹ Tilbake');")
        s=s.replace('button.textContent=labels[target[1]];','button.textContent=window.hnText(labels[target[1]]);')
        p.write_text(s,encoding='utf-8')
    p=renderer/'lib/hamnavigator-manual.js';s=p.read_text(encoding='utf-8')
    for value in ('Bruksanvisning','HamNavigator Map – bruksanvisning','Lukk','Søkbar bruksanvisning for HamNavigator Map'):
        s=s.replace("='"+value+"';","=window.hnText('"+value+"');")
        s=s.replace("setAttribute('aria-label','"+value+"')","setAttribute('aria-label',window.hnText('"+value+"'))")
    s=s.replace("frame.src='./HamNavigator-Map-bruksanvisning.html';","frame.src=window.hnEnglish?'./HamNavigator-Map-bruksanvisning.en.html':'./HamNavigator-Map-bruksanvisning.html';")
    s=s.replace("window.hnEnglish?'./HamNavigator-Map-bruksanvisning.en.html':'./HamNavigator-Map-bruksanvisning.html'","'./HamNavigator-Map-bruksanvisning'+(window.hnLanguage==='nb'?'':'.'+window.hnLanguage)+'.html'")
    p.write_text(s,encoding='utf-8')
    p=renderer/'lib/hamnavigator-delivery.js';s=p.read_text(encoding='utf-8')
    for text,colour in [('Åpne Map fra HamNavigator for felles leveringsstatus.','orange'),('Levering kunne ikke legges i kø. Kontakt lagret lokalt. Se Status og sikkerhetskopi.','orange'),('Logglevering registrert i HamNavigator. Se Status og sikkerhetskopi.','white')]:
        old="'<font style=\"color:"+colour+'">'+text+"</font>'"
        new=json.dumps('<font style="color:'+colour+'">')+'+window.hnText('+json.dumps(text,ensure_ascii=False)+')+"</font>"'
        s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
    print('Map language selector and Norwegian, English, Swedish menus installed')
if __name__=='__main__':install(HERE.parents[1]/'bygg/klient')
