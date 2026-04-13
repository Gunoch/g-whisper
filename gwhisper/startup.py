"""Manage 'start with Windows' via a shortcut in the Startup folder."""
import os
import sys

try:
    import win32com.client
    _WIN32 = True
except ImportError:
    _WIN32 = False


SHORTCUT_NAME = "g-whisper.lnk"


def _startup_folder():
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    )


def shortcut_path():
    return os.path.join(_startup_folder(), SHORTCUT_NAME)


def is_enabled():
    return _WIN32 and os.path.exists(shortcut_path())


def enable(target_bat, icon_ico=None):
    """Create a shortcut in Startup pointing to target_bat."""
    if not _WIN32:
        return False
    folder = _startup_folder()
    os.makedirs(folder, exist_ok=True)
    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortcut(shortcut_path())
    sc.Targetpath = os.path.abspath(target_bat)
    sc.WorkingDirectory = os.path.dirname(os.path.abspath(target_bat))
    sc.WindowStyle = 7  # minimized
    if icon_ico and os.path.exists(icon_ico):
        sc.IconLocation = os.path.abspath(icon_ico)
    sc.save()
    return True


def disable():
    if not _WIN32:
        return False
    try:
        os.remove(shortcut_path())
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False
