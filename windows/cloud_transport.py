"""HTTPS transport, including short-lived encrypted replies from the public gateway."""
import ui_language
import base64,io,json,os,re,time,urllib.request,urllib.error
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
PUBLIC_CLOUD='https://lb7yk.no/cloud'

def read_json(opener,request):
    with opener.open(request,timeout=20) as response:
        raw=response.read(40_000_001)
        if len(raw)>40_000_000:raise ValueError(ui_language.t('Serversvaret er for stort.'))
        return response.status,json.loads(raw)

def exchange(opener,request,base_url):
    reply_key=os.urandom(32)
    request.add_header('X-Ham-Reply-Key',base64.b64encode(reply_key).decode())
    status,data=read_json(opener,request)
    if status!=202:return data
    task=data.get('id','');receipt=data.get('receipt','')
    if not re.fullmatch('[a-f0-9]{32}',task) or not re.fullmatch('[a-f0-9]{64}',receipt):raise ValueError(ui_language.t('Ugyldig køsvar fra Cloud.'))
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        time.sleep(0.7)
        poll=urllib.request.Request(base_url.rstrip('/')+'/requests/'+task,headers={'Authorization':'Receipt '+receipt})
        status,envelope=read_json(opener,poll)
        if status==202:continue
        try:
            raw=AESGCM(reply_key).decrypt(base64.b64decode(envelope['nonce'],validate=True),base64.b64decode(envelope['data'],validate=True),task.encode())
            result=json.loads(raw);code=int(result['status']);payload=result['body']
        except Exception:raise ValueError(ui_language.t('Cloud-svaret kunne ikke bekreftes. Ingen lokale data er endret.')) from None
        if not 200<=code<300:raise urllib.error.HTTPError(request.full_url,code,'Cloud',{},io.BytesIO(json.dumps(payload).encode()))
        return payload
    raise ValueError(ui_language.t('Cloud-serveren svarte ikke i tide. Prøv igjen; lokale data er beholdt.'))
