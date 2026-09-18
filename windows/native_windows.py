"""Small Windows adapter: embed and restore an existing application's main HWND."""
import ui_language
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path

u = c.WinDLL('user32', use_last_error=True)
k = c.WinDLL('kernel32', use_last_error=True)
CALLBACK = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

def bind(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, args
    return fn

bind(u, 'EnumWindows', w.BOOL, CALLBACK, w.LPARAM)
bind(u, 'GetWindowThreadProcessId', w.DWORD, w.HWND, c.POINTER(w.DWORD))
bind(u, 'GetWindow', w.HWND, w.HWND, w.UINT)
bind(u, 'GetParent', w.HWND, w.HWND)
bind(u, 'SetParent', w.HWND, w.HWND, w.HWND)
bind(u, 'GetWindowLongPtrW', c.c_ssize_t, w.HWND, c.c_int)
bind(u, 'SetWindowLongPtrW', c.c_ssize_t, w.HWND, c.c_int, c.c_ssize_t)
bind(u, 'IsWindow', w.BOOL, w.HWND)
bind(u, 'IsWindowVisible', w.BOOL, w.HWND)
bind(u, 'GetWindowRect', w.BOOL, w.HWND, c.POINTER(w.RECT))
bind(u, 'GetClientRect', w.BOOL, w.HWND, c.POINTER(w.RECT))
bind(u, 'GetWindowTextW', c.c_int, w.HWND, w.LPWSTR, c.c_int)
bind(u, 'ShowWindow', w.BOOL, w.HWND, c.c_int)
bind(u, 'PostMessageW', w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
bind(u, 'SetFocus', w.HWND, w.HWND)
bind(u, 'GetForegroundWindow', w.HWND)
bind(u, 'GetAncestor', w.HWND, w.HWND, w.UINT)
bind(u, 'AttachThreadInput', w.BOOL, w.DWORD, w.DWORD, w.BOOL)
bind(u, 'GetCursorPos', w.BOOL, c.POINTER(w.POINT))
bind(u, 'WindowFromPoint', w.HWND, w.POINT)
bind(u, 'IsChild', w.BOOL, w.HWND, w.HWND)
bind(k, 'GetCurrentThreadId', w.DWORD)
bind(u, 'SetWindowPos', w.BOOL, w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT)
bind(k, 'OpenProcess', w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
bind(k, 'QueryFullProcessImageNameW', w.BOOL, w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD))
bind(k, 'CloseHandle', w.BOOL, w.HANDLE)

def pointer_activates_window(message):
    """Foreign child clicks reach their Qt container as WM_PARENTNOTIFY."""
    msg = w.MSG.from_address(int(message))
    return msg.message == 0x0210 and (msg.wParam & 0xffff) in (0x0201, 0x0204, 0x0207, 0x020b)


def executable_for(hwnd):
    pid = w.DWORD()
    u.GetWindowThreadProcessId(hwnd, c.byref(pid))
    process = k.OpenProcess(0x1000, False, pid.value)
    if not process:
        return None
    try:
        length = w.DWORD(32768)
        value = c.create_unicode_buffer(length.value)
        return Path(value.value) if k.QueryFullProcessImageNameW(process, 0, value, c.byref(length)) else None
    finally:
        k.CloseHandle(process)

def find_window(executable):
    """Choose the largest visible, unowned main window of this exact executable."""
    found = []
    @CALLBACK
    def visit(hwnd, _):
        if u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4) and executable_for(hwnd) == Path(executable):
            title = c.create_unicode_buffer(1024)
            u.GetWindowTextW(hwnd, title, 1024)
            name = Path(executable).name.lower()
            # Exclude splash screens and auxiliary Electron/Qt windows during startup.
            if name == 'radioassistentdigital.exe' and '(MSHV ' not in title.value:
                return True
            if name == 'hamnavigator.exe' and not title.value.startswith('HamNavigator 1.0'):
                return True
            if name == 'hamnavigatormap.exe' and not title.value.startswith('HamNavigator Map'):
                return True
            if name.startswith('mshv') and not ('MSHV' in title.value and 'version' in title.value.lower()):
                return True
            if name.startswith('gridtracker') and not title.value.startswith('GridTracker'):
                return True
            rect = w.RECT()
            u.GetWindowRect(hwnd, c.byref(rect))
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            if area > 10000:
                found.append((area, hwnd))
        return True
    u.EnumWindows(visit, 0)
    return max(found)[1] if found else None

class EmbeddedWindow:
    def __init__(self, hwnd, parent):
        if not u.IsWindow(hwnd):
            raise ValueError(ui_language.t('Programvinduet er lukket. Prøv igjen.'))
        self.hwnd, self.parent = hwnd, parent
        self.executable = executable_for(hwnd)
        self.previous_parent = u.GetParent(hwnd)
        self.style = u.GetWindowLongPtrW(hwnd, -16)
        self.exstyle = u.GetWindowLongPtrW(hwnd, -20)
        self.rect = w.RECT()
        u.GetWindowRect(hwnd, c.byref(self.rect))
        self.attached = False
        u.ShowWindow(hwnd, 9)
        # SetParent does not update WS_CHILD/WS_POPUP; explicitly remove the frame.
        u.SetWindowLongPtrW(hwnd, -16, (self.style & ~0x80CF0000) | 0x40000000)
        c.set_last_error(0)
        previous = u.SetParent(hwnd, parent)
        error = c.get_last_error()
        if not previous and error:
            u.SetWindowLongPtrW(hwnd, -16, self.style)
            raise OSError(error, ui_language.t('Windows kunne ikke bygge inn vinduet. Det kan brukes som eget vindu.'))
        self.attached = True
        self.resize()

    def alive(self):
        return bool(u.IsWindow(self.hwnd)) and executable_for(self.hwnd) == self.executable

    def resize(self):
        if self.attached and self.alive():
            rect = w.RECT()
            u.GetClientRect(self.parent, c.byref(rect))
            u.SetWindowPos(self.hwnd, None, 0, 0, rect.right, rect.bottom, 0x0034)

    def focus(self, from_pointer=False):
        """Give the foreign UI keyboard focus after Qt has activated its host."""
        if not self.attached or not self.alive():
            return
        if u.GetForegroundWindow() != u.GetAncestor(self.parent, 2):
            return  # Never pull focus back from another desktop application.
        if from_pointer:
            point = w.POINT()
            if not u.GetCursorPos(c.byref(point)):
                return
            under_pointer = u.WindowFromPoint(point)
            if under_pointer != self.hwnd and not u.IsChild(self.hwnd, under_pointer):
                return  # The user has already moved to another panel.
        own_thread = k.GetCurrentThreadId()
        target_thread = u.GetWindowThreadProcessId(self.hwnd, None)
        joined = own_thread != target_thread
        if joined and not u.AttachThreadInput(own_thread, target_thread, True):
            return
        try:
            u.SetFocus(self.hwnd)
        finally:
            if joined:
                u.AttachThreadInput(own_thread, target_thread, False)

    def detach(self):
        if self.attached and self.alive():
            c.set_last_error(0)
            u.SetParent(self.hwnd, self.previous_parent)
            error = c.get_last_error()
            if error:
                raise OSError(error, ui_language.t('Kunne ikke løsne programvinduet.'))
            u.SetWindowLongPtrW(self.hwnd, -16, self.style)
            u.SetWindowLongPtrW(self.hwnd, -20, self.exstyle)
            r = self.rect
            u.SetWindowPos(self.hwnd, None, r.left, r.top, r.right-r.left, r.bottom-r.top, 0x0074)
            u.ShowWindow(self.hwnd, 5)
        self.attached = False

    def request_close(self):
        """Restore the top-level window, then let the application close and save."""
        if not self.alive():
            return
        self.detach()
        if self.alive() and not u.PostMessageW(self.hwnd, 0x0010, 0, 0):
            raise OSError(c.get_last_error(), ui_language.t('Kunne ikke be programmet om å avslutte.'))
