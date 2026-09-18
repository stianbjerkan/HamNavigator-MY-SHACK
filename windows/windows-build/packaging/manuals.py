"""Bundle offline handbooks; no user profiles, network calls or radio state."""
from pathlib import Path
import html,re,shutil,json
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'klient'

CSS='''body{margin:0;background:#0e1923;color:#e1edf4;font:17px/1.65 system-ui,Segoe UI,sans-serif}main{max-width:1000px;margin:auto;padding:28px 24px 80px}h1{font-size:2.2rem;line-height:1.2}h2{font-size:1.35rem;color:#acebd9}a{color:#acebd9}p,li{overflow-wrap:anywhere}code{background:#24384a;padding:2px 5px;border-radius:3px;overflow-wrap:anywhere}header{border-bottom:1px solid #395063;padding-bottom:20px}nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:8px 18px;margin:20px 0}nav a{font-size:.92rem}section{scroll-margin-top:20px;border-top:1px solid #304659;padding-top:20px;margin-top:26px}label{display:block;margin-top:24px}input{box-sizing:border-box;width:100%;padding:12px;border-radius:6px;border:1px solid #617789;background:#142838;color:#fff;font:inherit}input:focus,a:focus{outline:2px solid #a2e5cf;outline-offset:3px}.meta{color:#9eb8c9}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.94rem}td,th{border:1px solid #476072;text-align:left;padding:10px}dt{font-weight:bold;color:#acebd9}dd{margin-bottom:12px}[hidden]{display:none!important}@media(max-width:600px){main{padding:18px 16px 50px}h1{font-size:1.7rem}}@media print{body{background:white;color:black;font-size:11pt}h2,a{color:black}main{max-width:none;padding:0}.search{display:none}nav{display:block}nav a{display:block}code{background:#eee}}'''
SEARCH='''const input=document.getElementById('search'),sections=[...document.querySelectorAll('main>section')],links=[...document.querySelectorAll('nav a')];input.addEventListener('input',()=>{const terms=input.value.toLocaleLowerCase('nb').trim().split(/\\s+/).filter(Boolean);let count=0;sections.forEach((s,i)=>{const match=terms.every(t=>s.textContent.toLocaleLowerCase('nb').includes(t));s.hidden=!match;links[i].hidden=!match;if(match)count++;});document.getElementById('results').textContent=count+' av '+sections.length+' kapitler';});'''

def chapters(language="nb"):
    page=(SOURCE/(f'languages/{language}/app.html' if language!='nb' else 'app.html')).read_text(encoding='utf-8')
    found=re.findall(r'<details class="manual-chapter card" id="manual-([^"]+)"[^>]*><summary>(.*?)</summary><div class="manual-body">(.*?)</div></details>',page,re.S)
    assert len(found)==33,'Review manual selections after changing chapter count.'
    return {key:(re.sub(r'^\d+ · ','',title),body) for key,title,body in found}

def standalone(title,items,intro,language="nb",name="HamNavigator.html"):
    toc=''.join(f'<a href="#{key}">{heading}</a>' for key,heading,body in items)
    sections=''.join(f'<section id="{key}"><h2>{i+1:02d} · {heading}</h2>{body}</section>' for i,(key,heading,body) in enumerate(items))
    page=f'''<!doctype html><html lang="nb"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} – bruksanvisning</title><style>{CSS}</style></head><body><main><header><p class="meta">LB7YK RadioLab · Bruksanvisning · 18. september 2026</p><h1>{html.escape(title)}</h1><p>{intro}</p><p class="meta">PC-pakke 1.9.16 · Mobile 0.5.3 · Cloud-funksjoner fra server 0.6.2</p></header><div class="search"><label for="search">Søk i bruksanvisningen</label><input type="search" id="search" placeholder="For eksempel passord, LoTW eller vannfall" maxlength="120"><p id="results" role="status" aria-live="polite">{len(items)} kapitler</p></div><nav aria-label="Kapitler">{toc}</nav>{sections}<footer><p>HamNavigator · LB7YK (Stian Bjerkan) · post@lb7yk.no. Opphavsopplysninger og lisenser følger installasjonen som tekstfiler.</p></footer></main><script>{SEARCH}</script></body></html>'''

    base=re.sub(r'\.(?:en|sv)\.html$','.html',name)
    choices=' '.join(f'<a href="{base if code=="nb" else base.replace(".html","."+code+".html")}" lang="{code}" hreflang="{code}">{label}</a>' for code,label in [('nb','Norsk'),('en','English'),('sv','Svenska')] if code!=language)
    page=page.replace('</header>',f'<p>{choices}</p></header>')
    if language=='en':
        replacements={'<html lang="nb"':'<html lang="en"',' – bruksanvisning':' – user guide','LB7YK RadioLab · Bruksanvisning · 18. september 2026':'LB7YK RadioLab · User guide · 18 September 2026','PC-pakke':'PC package','Cloud-funksjoner fra server':'Cloud features from server','Søk i bruksanvisningen':'Search this guide','For eksempel passord, LoTW eller vannfall':'For example password, LoTW or waterfall',' kapitler':' chapters','aria-label="Kapitler"':'aria-label="Chapters"',"' av '":"' of '","toLocaleLowerCase('nb')":"toLocaleLowerCase('en')",'Opphavsopplysninger og lisenser følger installasjonen som tekstfiler.':'Copyright notices and licences are included with the installation as text files.'}
        for old,new in replacements.items():page=page.replace(old,new)
    if language=='sv':
        replacements={'<html lang="nb"':'<html lang="sv"',' – bruksanvisning':' – bruksanvisning','LB7YK RadioLab · Bruksanvisning · 18. september 2026':'LB7YK RadioLab · Bruksanvisning · 18 september 2026','PC-pakke':'Datorpaket','Cloud-funksjoner fra server':'Cloud-funktioner från server','Søk i bruksanvisningen':'Sök i bruksanvisningen','For eksempel passord, LoTW eller vannfall':'Till exempel lösenord, LoTW eller vattenfall',' kapitler':' kapitel','aria-label="Kapitler"':'aria-label="Kapitel"',"toLocaleLowerCase('nb')":"toLocaleLowerCase('sv')",'Opphavsopplysninger og lisenser følger installasjonen som tekstfiler.':'Upphovsrättsuppgifter och licenser medföljer installationen som textfiler.'}
        for old,new in replacements.items():page=page.replace(old,new)
    return page

def generate(language="nb"):
    data=chapters(language);out=SOURCE/'manuals';out.mkdir(exist_ok=True)
    translations=json.loads((SOURCE/f'languages/manual-extras-{language}.json').read_text(encoding='utf-8')) if language!='nb' else {}
    def save(name,title,keys,intro,extra=()):
        items=[(key,*data[key]) for key in keys]+[(key,translations.get(heading,heading),translations.get(key,body)) for key,heading,body in extra]
        if language!='nb':name=name.replace('.html','.'+language+'.html')
        (out/name).write_text(standalone(title,items,translations.get(intro,intro),language,name),encoding='utf-8')
    save('HamNavigator.html','HamNavigator / MY SHACK',list(data),'Håndboken følger programmet og kan leses uten internett. Velg et kapittel eller søk etter det du vil gjøre.')
    save('HamNavigator-Digital.html','HamNavigator Digital',['start','digital','waterfall','clock','udp','direct','shared-log','services','lotw','status','backup','update'],
         'Radio, mottak, sending og felleslogg. MY SHACK har konto, Cloud og status. Digital har lyd, CAT/PTT og meldingsforløp.',[
         ('digital-workflow','Arbeidsrekkefølge for FT8/FT4','<ol><li>Velg egen stasjon, riktig modus og bånd. Kontroller radioens frekvens, USB/data-lyd, CAT/PTT og UTC.</li><li>Start mottak med <strong>MONITOR</strong> og kontroller dekodinger og lydnivå.</li><li>Velg motstasjon og riktig TX-periode/meldingsforløp i Digital. Automatisk dekoding er ikke det samme som automatisk sending.</li><li>Følg rapportutvekslingen og avslutningen. Kontroller at en fullført kontakt dukker opp i fellesloggen.</li><li><strong>STOP TX</strong> stopper sending. <strong>STOP MONITOR</strong> stopper mottak. Avslutt sending før du bytter radiooppsett eller oppdaterer.</li></ol><p>Valg og meldinger avhenger av modus og profil. Mobile har eget Auto TX-oppsett, beskrevet i mobilens bruksanvisning. MY SHACKs UDP-mottak styrer ikke senderen.</p>')])
    save('HamNavigator-Map.html','HamNavigator Map',['map','map-settings','udp','direct','shared-log','services','lotw','status','mobile-map','reference-map','backup','update'],
         'Kart, stasjoner, loggkilder og levering til loggtjenester. Åpne denne veiledningen med Bruksanvisning øverst i Map. Snarveier/F1 viser hurtigtastlisten.',[
         ('map-files','App-logg, lokale filer og feilsøking','<p>I <strong>Oppsett → Loggintegrasjoner</strong> viser <strong>App Log(s)</strong> filene Map følger fra loggprogrammene. Kontroller at den aktive <code>hamnavigator.adi</code> er med. Bruk <strong>Les lokal logg</strong> hvis en lagret kontakt ikke vises ennå. Ekstra filer under <strong>Local File(s)</strong> er egne datakilder; en gammel skrivebordskopi blir ikke automatisk den aktive fellesloggen.</p><p><strong>Importer logg</strong> leser en valgt fil i Map. Kontroller MY SHACK før du regner med at en Map-import er i den felles Cloud-loggen. Bruk MY SHACKs <strong>Importer ADIF</strong> når kontaktene skal inn i fellesloggen.</p><p>Tomt bakgrunnskart kan skyldes kartfliser/nett; manglende stasjoner kan skyldes UDP eller filtre; manglende QSO-er kan skyldes feil loggfil eller at kontakten ikke er fullført og lagret. Loggkontoer endres under Loggintegrasjoner; programtilkoblingen endres under Stasjon og tilkobling.</p>')])
    # Digital uses QTextBrowser, not a web browser: no script/form controls.
    digital=(out/(f'HamNavigator-Digital.{language}.html' if language!='nb' else 'HamNavigator-Digital.html')).read_text(encoding='utf-8')
    digital=re.sub(r'<div class="search">.*?</div>','',digital,flags=re.S)
    digital=re.sub(r'<script>.*?</script>','',digital,flags=re.S)
    digital=re.sub(r'<style>.*?</style>','<style>body{font-family:Segoe UI;font-size:12pt;color:#e1edf4}h1,h2,a{color:#acebd9}td,th{padding:8px}code{color:#acebd9}</style>',digital,flags=re.S)
    digital=digital.replace('<body>','<body bgcolor="#0e1923">')
    digital=re.sub(r'<nav[^>]*>(.*?)</nav>',lambda m:'<h2>Kapitler</h2>'+re.sub(r'(<a .*?</a>)',r'<p>\1</p>',m[1]),digital,flags=re.S)
    digital=re.sub(r'<section id="([^"]+)">',r'<a name="\1"></a>',digital).replace('</section>','')
    digital=digital.replace('HamNavigator-Digital.sv.html','qrc:/branding/help-sv.html').replace('HamNavigator-Digital.en.html','qrc:/branding/help-en.html').replace('HamNavigator-Digital.html','qrc:/branding/help.html')
    if language!='nb':digital=digital.replace('<h2>Kapitler</h2>','<h2>'+('Kapitel' if language=='sv' else 'Chapters')+'</h2>')
    (out/(f'HamNavigator-Digital-Qt.{language}.html' if language!='nb' else 'HamNavigator-Digital-Qt.html')).write_text(digital,encoding='utf-8')
    if language=='nb':
        generate('en');generate('sv')
    return out

def install(bundle):
    out=generate();bundle=Path(bundle)
    shutil.copytree(out,bundle/'manuals',dirs_exist_ok=True)
    renderer=bundle/'release/HamNavigator-Map/resources/app/src/renderer'
    shutil.copy2(out/'HamNavigator-Map.html',renderer/'HamNavigator-Map-bruksanvisning.html')
    shutil.copy2(out/'HamNavigator-Map.en.html',renderer/'HamNavigator-Map-bruksanvisning.en.html')
    shutil.copy2(out/'HamNavigator-Map.sv.html',renderer/'HamNavigator-Map-bruksanvisning.sv.html')
    shutil.copy2(HERE/'map_manual.js',renderer/'lib/hamnavigator-manual.js')
    path=renderer/'GridTracker2.html';page=path.read_text(encoding='utf-8')
    if 'hamnavigator-manual.js' not in page:
        assert '</head>' in page
        path.write_text(page.replace('</head>','<script src="./lib/hamnavigator-manual.js" defer></script></head>'),encoding='utf-8')
    for language in ('en','ru'):
        dest=bundle/f'release/HamNavigator/settings/resources/url_help/{language}/help_{language}.html'
        assert dest.is_file(),dest
        # Preserve the legacy resource locations; the Russian slot uses our
        # Norwegian fallback, while Swedish has its own embedded Qt resource.
        source='HamNavigator-Digital-Qt.en.html' if language=='en' else 'HamNavigator-Digital-Qt.html'
        shutil.copy2(out/source,dest)
    rebuilt=HERE.parent.parent/'bygg/digital-manual/bin/HamNavigator.exe'
    if not rebuilt.exists():raise RuntimeError('Build Digital with the current embedded handbook first.')
    shutil.copy2(rebuilt,bundle/'release/HamNavigator/HamNavigator.exe')

if __name__=='__main__':generate()
