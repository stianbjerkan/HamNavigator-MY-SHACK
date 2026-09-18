"""Verified GitHub release downloads, independent of the user interface."""
from __future__ import annotations
import ui_language
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'stianbjerkan/HamNavigator-MY-SHACK'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
ASSET_NAME = 'HamNavigator-MY-SHACK-Setup.exe'


class UpdateCancelled(Exception):
    pass


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value))
    if not match:
        raise ValueError(ui_language.t('Utgivelsen har et ukjent versjonsnummer.'))
    return tuple(map(int, match.groups()))


def current_version(root):
    value = (Path(root) / 'VERSION').read_text(encoding='utf-8').strip()
    version_tuple(value)
    return value


def release_info(payload, installed):
    """Accept only stable releases and this repository's exact installer asset."""
    tag = payload.get('tag_name', '')
    if payload.get('draft') or payload.get('prerelease'):
        return None
    if version_tuple(tag) <= version_tuple(installed):
        return None
    asset = next((a for a in payload.get('assets', []) if a.get('name') == ASSET_NAME), None)
    if not asset:
        raise ValueError(ui_language.t('Den nye utgivelsen mangler installasjonsfilen. Prøv igjen senere.'))
    digest = asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
        raise ValueError(ui_language.t('Utgivelsen mangler en gyldig kontrollsum. Oppdateringen kan ikke startes.'))
    expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET_NAME}'
    if asset.get('browser_download_url') != expected:
        raise ValueError(ui_language.t('Utgivelsen har en uventet nedlastingsadresse.'))
    size = asset.get('size')
    if type(size) is not int or not 0 < size < 2 * 1024**3:
        raise ValueError(ui_language.t('Utgivelsen har en ugyldig filstørrelse.'))
    return {'version': tag.removeprefix('v'), 'url': expected, 'size': size,
            'sha256': digest[7:].lower()}


def check_update(installed, opener=urllib.request.urlopen):
    req = urllib.request.Request(API_URL, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'HamNavigator-MY-SHACK/' + installed,
        'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with opener(req, timeout=25) as response:
            payload = json.loads(response.read(2 * 1024**2))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(ui_language.t('Ingen tilgjengelig utgivelse på GitHub ennå.')) from exc
        if exc.code in (403, 429):
            raise ValueError(ui_language.t('GitHub begrenser oppdateringssjekker akkurat nå. Prøv igjen senere.')) from exc
        raise
    return release_info(payload, installed)


def download_update(info, cache, progress, cancel, opener=urllib.request.urlopen):
    version_tuple(info['version'])
    folder = Path(cache) / ('v' + info['version'])
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ASSET_NAME
    part = target.with_suffix('.exe.part')
    digest, received = hashlib.sha256(), 0
    try:
        req = urllib.request.Request(info['url'], headers={'User-Agent': 'HamNavigator-MY-SHACK'})
        with opener(req, timeout=30) as response, part.open('wb') as output:
            if urllib.parse.urlsplit(response.geturl()).scheme != 'https':
                raise ValueError(ui_language.t('Nedlastingen bruker ikke en sikker forbindelse.'))
            while True:
                if cancel.is_set():
                    raise UpdateCancelled()
                block = response.read(1024 * 1024)
                if not block:
                    break
                received += len(block)
                if received > info['size']:
                    raise ValueError(ui_language.t('Nedlastingen har feil filstørrelse.'))
                digest.update(block)
                output.write(block)
                progress(received, info['size'])
        if cancel.is_set():
            raise UpdateCancelled()
        if received != info['size'] or digest.hexdigest() != info['sha256']:
            raise ValueError(ui_language.t('Kontrollsummen stemmer ikke. Last ned oppdateringen på nytt.'))
        os.replace(part, target)
        return target
    finally:
        part.unlink(missing_ok=True)


def installer_arguments(root):
    root = Path(root).resolve()
    args = ['/NORESTART', '/SP-']
    # A development checkout must never become an installation destination.
    if (root / 'BUNDLE.json').is_file() and (root / 'Radioassistent.exe').is_file():
        args.append('/DIR=' + str(root))
    return args
