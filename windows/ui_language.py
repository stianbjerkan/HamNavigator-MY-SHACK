"""Local UI language. No account data, logs or radio settings are modified."""
import json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
LANGUAGES={'nb','en','sv'}
def directory():
    return Path(os.environ.get('RADIOASSISTENT_DATA',str(Path(os.environ.get('APPDATA',str(ROOT)))/'Radioassistent')))
def get():
    override=os.environ.get('HAMNAVIGATOR_LANGUAGE')
    if override in LANGUAGES:return override
    try:code=json.loads((directory()/'ui-language.json').read_text(encoding='utf-8')).get('language','nb')
    except (OSError,ValueError,AttributeError):return 'nb'
    return code if code in LANGUAGES else 'nb'
def select(code):
    if not isinstance(code,str) or code not in LANGUAGES:raise ValueError('Unsupported language')
    folder=directory();folder.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='ui-language-',suffix='.tmp',dir=folder)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump({'language':code},stream);stream.flush();os.fsync(stream.fileno())
        os.replace(name,folder/'ui-language.json')
    finally:
        if os.path.exists(name):os.unlink(name)
    return code
_catalogs=None
_reverse=None

def catalogs():
    global _catalogs,_reverse
    if _catalogs is None:
        values={}
        for code in ('en','sv'):
            try:values[code]=json.loads((ROOT/f'languages/{code}.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):values[code]={}
        reverse={}
        for catalog in values.values():
            for key,value in catalog.items():
                if value!=key and 'Ã' not in key and 'Â' not in key:reverse.setdefault(value,key)
        _reverse=reverse;_catalogs=values
    return _catalogs
def t(source):
    if not isinstance(source,str):return source
    values=catalogs();code=get()
    # A source-language key wins over a reverse alias with the same spelling.
    original=source if source in values['en'] else _reverse.get(source,source)
    return values.get(code,{}).get(original,original)

def canonical(source):
    """Normalize fixed diagnostic labels before storing them, independent of UI language."""
    values=catalogs()
    return source if source in values['en'] else _reverse.get(source,source)
def modules(catalog):
    return [{**item,'title':t(item.get('title','')),'description':t(item.get('description',''))} for item in catalog]
