"""Apply and verify Windows branding, without changing program code or profiles.

Usage: python app_identity.py BUNDLE_ROOT [--version 1.9.1]
The upstream notices stay in OPPHAV.txt and the supplied license/source files.
"""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import struct
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent.parent
RCEDIT_URL = 'https://github.com/electron/rcedit/releases/download/v2.0.0/rcedit-x64.exe'
# Pinned official release binary, retrieved over verified HTTPS on 2026-09-12.
RCEDIT_SHA256 = '3e7801db1a5edbec91b49a24a094aad776cb4515488ea5a4ca2289c400eade2a'
PRODUCTS = {
    'Radioassistent.exe': 'HamNavigator MY SHACK',
    'release/HamNavigator/HamNavigator.exe': 'HamNavigator Digital',
    'release/HamNavigator-Map/HamNavigatorMap.exe': 'HamNavigator Map',
}
FIELDS = ('FileDescription', 'ProductName', 'CompanyName', 'InternalName',
          'OriginalFilename', 'FileVersion', 'ProductVersion', 'LegalCopyright', 'Comments')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def editor():
    tool = SERVER / 'bygg/tools/rcedit-x64.exe'
    tool.parent.mkdir(parents=True, exist_ok=True)
    if not tool.exists():
        with urllib.request.urlopen(RCEDIT_URL, timeout=60) as response:
            data = response.read(2 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != RCEDIT_SHA256:
            raise RuntimeError('Resource editor checksum mismatch')
        tool.write_bytes(data)
    if sha256(tool) != RCEDIT_SHA256:
        raise RuntimeError('Resource editor checksum mismatch')
    return tool


def pe_sections(path):
    """Hash every original section except resources; resource editing must preserve code."""
    data = Path(path).read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    assert data[pe:pe+4] == b'PE\0\0'
    count = struct.unpack_from('<H', data, pe + 6)[0]
    optional_size = struct.unpack_from('<H', data, pe + 20)[0]
    start = pe + 24 + optional_size
    result = {}
    for i in range(count):
        entry = start + i * 40
        name = data[entry:entry+8].rstrip(b'\0').decode('ascii')
        virtual_size, _, raw_size, offset = struct.unpack_from('<IIII', data, entry + 8)
        if name != '.rsrc':
            result[name] = hashlib.sha256(data[offset:offset+min(virtual_size, raw_size)]).hexdigest()
    return result


def version_info(path):
    """Read every language in the actual Win32 VERSIONINFO resource."""
    api = ctypes.WinDLL('version', use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    api.VerQueryValueW.restype = wintypes.BOOL
    ignored = wintypes.DWORD()
    size = api.GetFileVersionInfoSizeW(str(path), ctypes.byref(ignored))
    if not size:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(path), 0, size, buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    assert api.VerQueryValueW(buffer, '\\VarFileInfo\\Translation', ctypes.byref(pointer), ctypes.byref(length))
    translation = ctypes.string_at(pointer, length.value)
    values = {}
    for language, codepage in struct.iter_unpack('<HH', translation):
        key = f'{language:04x}{codepage:04x}'
        values[key] = {}
        for field in FIELDS:
            query = f'\\StringFileInfo\\{key}\\{field}'
            if api.VerQueryValueW(buffer, query, ctypes.byref(pointer), ctypes.byref(length)):
                values[key][field] = ctypes.wstring_at(pointer, max(0, length.value - 1))
    return values


def verify_file(path, product, version):
    values = version_info(path)
    assert values, f'No version information: {path}'
    for language, fields in values.items():
        assert fields.get('FileDescription') == product, (path, language, fields)
        assert fields.get('ProductName') == product, (path, language, fields)
        assert fields.get('CompanyName') == 'LB7YK RadioLab', (path, fields)
        assert fields.get('ProductVersion') == version, (path, fields)
        assert all(old not in json.dumps(fields).lower() for old in ('gridtracker', 'mshv')), (path, fields)
    return values


def brand_map_source(app, version):
    package_file = app / 'package.json'
    package = json.loads(package_file.read_text(encoding='utf-8'))
    package.update(name='hamnavigator-map', productName='HamNavigator Map',
                   description='HamNavigator Map – kart og stasjonsoversikt',
                   author='LB7YK RadioLab – Stian Bjerkan', homepage='https://lb7yk.no')
    # Keep engine version and dependency keys for compatibility. Edition version is explicit.
    package['hamnavigatorVersion'] = version
    package_file.write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    main = app / 'src/main/index.js'
    text = main.read_text(encoding='utf-8')
    text = text.replace('To launch GridTracker2 from command line', 'To launch HamNavigator Map from command line')
    text = text.replace('GridTracker2 starting up!', 'HamNavigator Map starting up!')
    main.write_text(text, encoding='utf-8')
    assert 'GridTracker' in (app / 'OPPHAV.txt').read_text(encoding='utf-8')


def apply(bundle, version):
    bundle = Path(bundle).resolve()
    tool = editor()
    icon = HERE / 'hamnavigator.ico'
    assert icon.is_file(), 'HamNavigator icon is missing'
    # Never silently relabel signed binaries; signing must follow the resource step.
    report = {'version': version, 'products': []}
    for relative, product in PRODUCTS.items():
        path = bundle / relative
        header = path.read_bytes()[:1024]
        pe = struct.unpack_from('<I', header, 0x3c)[0]
        optional = pe + 24
        directories = optional + (112 if struct.unpack_from('<H', header, optional)[0] == 0x20b else 96)
        assert struct.unpack_from('<II', header, directories + 4 * 8) == (0, 0), f'Signed input requires explicit signing workflow: {path}'
        before_sections = pe_sections(path)
        before = version_info(path)
        values = {
            'FileDescription': product, 'ProductName': product, 'CompanyName': 'LB7YK RadioLab',
            'InternalName': product.replace(' ', ''), 'OriginalFilename': path.name,
            'LegalCopyright': 'HamNavigator-utgaven © 2026 LB7YK (Stian Bjerkan). Opphav og lisenser: OPPHAV.txt.',
            'Comments': 'HamNavigator-utgaven: programmert og designet av LB7YK (Stian Bjerkan).',
        }
        args = [str(tool), str(path), '--set-icon', str(icon), '--set-file-version', version, '--set-product-version', version]
        for key, value in values.items():
            args.extend(['--set-version-string', key, value])
        subprocess.run(args, check=True, capture_output=True, text=True)
        after_sections = pe_sections(path)
        assert before_sections == after_sections, f'Non-resource section changed: {path}'
        after = verify_file(path, product, version)
        report['products'].append({'path': relative, 'before': before, 'after': after, 'code_and_data_unchanged': True, 'sha256': sha256(path)})
    brand_map_source(bundle / 'release/HamNavigator-Map/resources/app', version)
    assert 'MSHV' in (bundle / 'release/HamNavigator/OPPHAV.txt').read_text(encoding='utf-8')
    (bundle / 'OPPHAV.txt').write_text(
        'HamNavigator-utgaven: programmert og designet av LB7YK (Stian Bjerkan).\n'
        'Digital er basert på MSHV. Map er basert på GridTracker.\n'
        'Fullstendige opphavsopplysninger og lisenser følger i komponentenes OPPHAV.txt og lisensfiler.\n', encoding='utf-8')
    return report


def refresh_checksums(bundle):
    for component in ('HamNavigator', 'HamNavigator-Map'):
        folder = Path(bundle) / 'release' / component
        manifest = folder / 'SHA256SUMS.txt'
        if manifest.exists():
            lines = []
            for line in manifest.read_text(encoding='utf-8').splitlines():
                parts = line.split('  ', 1)
                if len(parts) == 2 and (folder / parts[1]).is_file():
                    lines.append(sha256(folder / parts[1]) + '  ' + parts[1])
            manifest.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--version', default='1.9.1')
    args = parser.parse_args()
    report = apply(args.bundle, args.version)
    refresh_checksums(args.bundle)
    output = SERVER / 'tester' / f'windows-identity-{args.version}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: Windows names verified for MY SHACK, Digital and Map. Program code and data sections are unchanged.')
