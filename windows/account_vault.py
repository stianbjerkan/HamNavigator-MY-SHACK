"""Authenticated encryption for account settings; no plaintext secrets on server."""
import ui_language
import base64, hashlib, hmac, json, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

PRIVATE_KEYS={'map/preferences','digital/preferences','setting/preferences','panels/preferences'}
def b64(value):return base64.urlsafe_b64encode(value).decode('ascii')
def un64(value):return base64.urlsafe_b64decode(value.encode('ascii'))
def fingerprint(key):return hashlib.sha256(key).hexdigest()
def password_key(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,600000,32)
def seal(key,value,aad):
    nonce=os.urandom(12);raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
    return {'encrypted':'AES-256-GCM','nonce':b64(nonce),'data':b64(AESGCM(key).encrypt(nonce,raw,aad.encode()))}
def open_sealed(key,value,aad):
    try:
        if not isinstance(value,dict) or value.get('encrypted')!='AES-256-GCM':raise ValueError()
        return json.loads(AESGCM(key).decrypt(un64(value['nonce']),un64(value['data']),aad.encode()))
    except (InvalidTag,ValueError,TypeError,KeyError):raise ValueError(ui_language.t('Krypterte innstillinger kan ikke åpnes. Ingen lokale innstillinger er overskrevet.')) from None
def wrap(key,password,user):
    salt=os.urandom(16)
    return {'version':1,'salt':b64(salt),'check':fingerprint(key),'wrapped':seal(password_key(password,salt),b64(key),'HamNavigator key '+user)}
def unwrap(value,password,user):
    key=un64(open_sealed(password_key(password,un64(value['salt'])),value['wrapped'],'HamNavigator key '+user))
    if len(key)!=32 or not hmac.compare_digest(fingerprint(key),value['check']):raise ValueError(ui_language.t('Ugyldig kontonøkkel.'))
    return key
def recovery_key(text):
    value=text.strip().removeprefix('HN1-');key=un64(value)
    if len(key)!=32:raise ValueError(ui_language.t('Ugyldig gjenopprettingsnøkkel.'))
    return key
