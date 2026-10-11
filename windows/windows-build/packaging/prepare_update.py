"""Installer preflight: normal shutdown before Restart Manager and file copying.

Uses the existing shell's named pipe without importing the installed Qt stack.
Works with old Update buttons. Falls back to --close for legacy shells. Never kills.
"""
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ORIGIN = 'http://127.0.0.1:18763'


def request_shell_close(root, pending, *, running=None):
    """Send the old shell's existing 'close' command to a verified local peer.

    Pipe names include the installation path, port and user. Enumerating this
    prefix and checking the server PID avoids path-casing/environment guesses.
    No command is sent to another installation. No GUI/runtime is started.
    """
    running = running or processes_in
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    kernel.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    kernel.SetNamedPipeHandleState.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
                                              ctypes.c_void_p, ctypes.c_void_p]
    kernel.SetNamedPipeHandleState.restype = wintypes.BOOL
    sent = set()
    for name in os.listdir('\\\\.\\pipe\\'):
        if not re.fullmatch(r'Radioassistent-[0-9a-f]{20}', name):
            continue
        try:
            pipe = open('\\\\.\\pipe\\' + name, 'r+b', buffering=0)
        except OSError as exc:
            # A server can exit or have all instances busy while enumerating.
            if exc.winerror in (2, 5, 231):
                continue
            raise
        with pipe:
            handle = msvcrt.get_osfhandle(pipe.fileno())
            pid = wintypes.ULONG()
            if not kernel.GetNamedPipeServerProcessId(handle, ctypes.byref(pid)):
                raise ctypes.WinError(ctypes.get_last_error())
            if pid.value not in pending or pid.value not in running(root) or pid.value in sent:
                continue
            # Never hang waiting for a wedged event loop to read/flush. The
            # normal byte-mode Qt pipe has room for this five-byte command.
            mode = wintypes.DWORD(1)  # PIPE_READMODE_BYTE | PIPE_NOWAIT
            if not kernel.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
                raise ctypes.WinError(ctypes.get_last_error())
            if pipe.write(b'close') != 5:
                raise OSError('Incomplete normal shutdown request')
            sent.add(pid.value)
    return sent


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
        return info
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
            close_backend=stop_backend, close_shell=request_shell_close,
            report=lambda **entry: None):
    root = Path(root).resolve()
    pending = running(root)
    report(phase='process_check', pending_pids=sorted(pending))
    if not pending:
        return
    sent = close_shell(root, pending)
    report(phase='direct_shell_close', sent_pids=sorted(sent))
    lone_backend = not sent and len(pending) == 1 and inspect_backend(root, pending) is not None
    if lone_backend:
        # Newer buttons can close the shell before setup gets here. A verified
        # lone backend needs no second graphical --close process.
        report(phase='backend_without_shell', pid=next(iter(pending)))
    if not sent and not lone_backend:
        # Retain compatibility with legacy/no-pipe clients. A successful pipe
        # request must never restart/import the old Qt stack for a second close.
        client = root/'desktop_host.py'
        python = root/'runtime/pythonw.exe'
        if not client.is_file() or not python.is_file():
            raise RuntimeError('No running shell or legacy shutdown entry point')
        report(phase='legacy_close_start')
        launch([str(python), str(client), '--close'], cwd=str(root), timeout=12,
               check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = now() + timeout
    requested_backend = False
    last_pending = None
    while True:
        pending = running(root)
        if pending != last_pending:
            report(phase='waiting', pending_pids=sorted(pending))
            last_pending = pending
        if not pending:
            return
        # Recover a lone backend only after every GUI/Map/Digital process exits.
        if not requested_backend and len(pending) == 1:
            info = inspect_backend(root, pending)
            if info is not None:
                pid = info['pid']
                if info.get('stopping'):
                    # The shell already requested shutdown. Its backend may
                    # still be finishing a sync/disk flush; do not POST again.
                    report(phase='backend_already_stopping', pid=pid)
                else:
                    report(phase='matching_backend_close', pid=pid)
                    try:
                        close_backend()
                    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
                        # The shell can start shutdown between health and POST.
                        # Old backends return 503 while stopping. Accept only
                        # that status or a lost connection, and only after
                        # verifying exit or the SAME backend's stopping state.
                        status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
                        if status is not None and status != 503:
                            raise
                        remaining = running(root)
                        current = inspect_backend(root, remaining) if remaining == {pid} else None
                        if remaining and not (current and current['pid'] == pid and current.get('stopping')):
                            raise
                        report(phase='backend_shutdown_race', pid=pid,
                               error_type=type(exc).__name__, http_status=status)
                # A stop request/observed shutdown is not completion. Continue
                # checking actual process exit; failed saving still times out.
                requested_backend = True
        if now() >= deadline:
            raise TimeoutError('Normal shutdown incomplete; no files replaced')
        pause(.25)


def main(argv):
    def report(**entry):
        # Only bounded diagnostic fields, never account data, environment,
        # exception messages or command arguments from installed applications.
        if len(argv) > 1:
            with Path(argv[1]).open('a', encoding='ascii') as stream:
                stream.write(json.dumps(entry, ensure_ascii=True) + '\n')
    try:
        prepare(Path(argv[0]), report=report)
        report(phase='ready')
        print('HamNavigator is closed and ready for update.')
    except Exception as exc:
        report(phase='failed', error_type=type(exc).__name__,
               child_exit=getattr(exc, 'returncode', None),
               winerror=getattr(exc, 'winerror', None), errno=getattr(exc, 'errno', None),
               http_status=exc.code if isinstance(exc, urllib.error.HTTPError) else None)
        print('HamNavigator could not finish saving and closing. No files replaced.')
        return 2 if isinstance(exc, TimeoutError) else 3
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
