"""Poll normal window-close requests without killing processes or blocking Qt."""
import ui_language
import time


class ProgramShutdown:
    def __init__(self, windows, starting, timeout=20, clock=time.monotonic):
        self.windows, self.starting, self.clock = windows, starting, clock
        self.deadline = clock() + timeout
        self.requested = set()

    def poll(self):
        pending = []
        for window in self.windows():
            if not window.alive():
                continue
            if window.hwnd not in self.requested:
                window.request_close()
                self.requested.add(window.hwnd)
            if window.alive():
                pending.append(window)
        if not pending and not self.starting():
            return True
        if self.clock() >= self.deadline:
            raise TimeoutError(ui_language.t('HamNavigator eller Map er ikke ferdig med å lukke. Fullfør eventuelle dialoger i programmene, og lukk MY SHACK igjen.'))
        return False
