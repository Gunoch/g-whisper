"""Single-instance lock using a Windows named mutex."""
import sys

try:
    import win32event
    import win32api
    import winerror
    _WIN32 = True
except ImportError:
    _WIN32 = False


MUTEX_NAME = "Global\\g-whisper-single-instance"


class SingleInstance:
    """Context-manager-style named mutex on Windows, no-op elsewhere."""

    def __init__(self, name=MUTEX_NAME):
        self.name = name
        self.handle = None
        self.already_running = False

    def acquire(self):
        if not _WIN32:
            return True
        self.handle = win32event.CreateMutex(None, False, self.name)
        last_error = win32api.GetLastError()
        if last_error == winerror.ERROR_ALREADY_EXISTS:
            self.already_running = True
            return False
        return True

    def release(self):
        if self.handle:
            try:
                win32api.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
