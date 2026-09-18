"""Installer preflight: normal shutdown before Restart Manager and file copying.

Works with already installed desktop_host.py --close versions. Never kills.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ORIGIN = 'http://127.0.0.1:18763'


def processes_in(root):
    root = os.path.normcase(str(Path(root).resolve())) + os.sep
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    pids = (wintypes.DWORD * 32768)()
    used = wintypes.DWORD()
    if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(used)):
        raise OSError('Cannot enumerate processes')
    if used.value == ctypes.sizeof(pids):
        raise OSError('Incomplete process list')
    result = set()
    for pid in pids[:used.value // ctypes.sizeof(wintypes.DWORD)]:
        if not pid or pid == os.getpid():
            continue
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                if os.path.normcase(path.value).startswith(root):
                    result.add(pid)
        finally:
            kernel.CloseHandle(handle)
    return result


def backend(root, pids):
    # Never stop another app or another HamNavigator installation.
    try:
        with urllib.request.urlopen(ORIGIN+'/api/health', timeout=2) as response:
            info = json.load(response)
        if (info.get('app') not in ('Radioassistent', 'HamNavigator MY SHACK')
                or info.get('pid') not in pids or not info.get('can_stop')
                or os.path.normcase(str(Path(info.get('root', '')).resolve()))
                != os.path.normcase(str(root))):
            return None
        return info['pid']
    except (OSError, ValueError):
        return None


def stop_backend():
    with urllib.request.urlopen(ORIGIN, timeout=3) as response:
        token = re.search(r'name="radio-token" content="([^"]+)"', response.read(2_000_000).decode()).group(1)
    request = urllib.request.Request(ORIGIN+'/api/backend/stop', b'{}',
        {'Content-Type': 'application/json', 'X-Radio-Token': token})
    with urllib.request.urlopen(request, timeout=5) as response:
        json.load(response)


def prepare(root, timeout=45, *, running=processes_in, now=time.monotonic,
            pause=time.sleep, launch=subprocess.run, inspect_backend=backend,
            close_backend=stop_backend):
    root = Path(root).resolve()
    if not running(root):
        return
    client = root/'desktop_host.py'
    python = root/'runtime/pythonw.exe'
    if not client.is_file() or not python.is_file():
        raise RuntimeError('Close programs in the installation folder first')
    # The shell saves layout, asks Digital/Map to save and close, then flushes
    # log/sync state. A rejected close or failed save keeps the processes alive.
    launch([str(python), str(client), '--close'], cwd=str(root), timeout=12,
           check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = now() + timeout
    requested_backend = False
    while True:
        pending = running(root)
        if not pending:
            return
        # Recover a lone backend only after every GUI/Map/Digital process exits.
        if not requested_backend and len(pending) == 1:
            pid = inspect_backend(root, pending)
            if pid is not None:
                close_backend()
                requested_backend = True
        if now() >= deadline:
            raise TimeoutError('Normal shutdown incomplete; no files replaced')
        pause(.25)


if __name__ == '__main__':
    try:
        prepare(Path(sys.argv[1]))
        print('HamNavigator is closed and ready for update.')
    except Exception:
        # No credentials or Python exception details in installer output.
        print('HamNavigator could not finish saving and closing. No files replaced.')
        sys.exit(2)
