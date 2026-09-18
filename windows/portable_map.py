"""Local POTA/SOTA point catalogue; public data, no account or log upload."""
import ui_language
import csv, io, json, math, threading, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT/'map-data/catalogue.json'
SOURCES = {'POTA':'https://pota.app/all_parks_ext.csv', 'SOTA':'https://storage.sota.org.uk/summitslist.csv'}
_cache = None
_lock = threading.Lock()

def parse_catalogue(data, program, today):
    try: text = data.decode('utf-8-sig')
    except UnicodeDecodeError: text = data.decode('latin-1')
    if program == 'SOTA': text = text[text.index('SummitCode,'):]
    result = []
    for row in csv.DictReader(io.StringIO(text, newline=None)):
        try:
            if program == 'POTA':
                if row['active'] != '1': continue
                ref,name,lat,lon = row['reference'],row['name'],float(row['latitude']),float(row['longitude'])
                extra = {'region':row['locationDesc']}
            else:
                start = datetime.strptime(row['ValidFrom'], '%d/%m/%Y').date()
                end = datetime.strptime(row['ValidTo'], '%d/%m/%Y').date()
                if not start <= today <= end: continue
                ref,name,lat,lon = row['SummitCode'],row['SummitName'],float(row['Latitude']),float(row['Longitude'])
                extra = {'region':row['AssociationName']+' / '+row['RegionName'], 'height':int(row['AltM']), 'points':int(row['Points'])}
            if not math.isfinite(lat+lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180: continue
            result.append(dict(program=program,ref=ref,name=name,lat=lat,lon=lon,**extra))
        except (ValueError,KeyError): continue
    return result

def update_catalogue():
    global _cache
    with _lock:
        now=datetime.now(timezone.utc)
        items=[]
        for program,url in SOURCES.items():
            req=urllib.request.Request(url,headers={'User-Agent':'Radioassistent-HamNavigator/1.0'})
            with urllib.request.urlopen(req,timeout=45) as response: raw=response.read(80_000_000)
            rows=parse_catalogue(raw,program,now.date())
            if len(rows)<1000: raise ValueError('Ufullstendig '+program+ui_language.t('-register. Forrige kartdata beholdes.'))
            items.extend(rows)
        value={'updated':now.isoformat(), 'sources':SOURCES, 'items':items}
        DATA.parent.mkdir(exist_ok=True)
        temp=DATA.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temp.replace(DATA)
        _cache=value
        return {'updated':value['updated'],'count':len(items)}

def catalogue():
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                if not DATA.exists(): raise ValueError(ui_language.t('Kartregister mangler. Trykk Oppdater kartdata.'))
                _cache=json.loads(DATA.read_text(encoding='utf-8'))
    return _cache

def query(args):
    value=catalogue();items=value['items']
    programs=set(args.get('programs','POTA,SOTA').upper().split(','))
    search=args.get('q','').strip().casefold()[:100]
    if search:
        rows=[r for r in items if r['program'] in programs and search in (r['ref']+' '+r['name']).casefold()]
        rows.sort(key=lambda r:(r['ref'].casefold()!=search,not r['ref'].casefold().startswith(search),r['ref']))
        limit=40
    else:
        box=[float(args.get(k,d)) for k,d in [('west',-180),('south',-90),('east',180),('north',90)]]
        w,s,e,n=box
        if not all(math.isfinite(x) for x in box) or not(-180<=w<=180 and -180<=e<=180 and -90<=s<=n<=90): raise ValueError(ui_language.t('Ugyldig kartutsnitt.'))
        rows=[r for r in items if r['program'] in programs and s<=r['lat']<=n and ((w<=r['lon']<=e) if w<=e else (r['lon']>=w or r['lon']<=e))]
        limit=2500
    return {'updated':value['updated'],'total':len(rows),'truncated':len(rows)>limit,'items':rows[:limit]}

if __name__=='__main__':print(update_catalogue())
