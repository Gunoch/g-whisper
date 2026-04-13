"""Windows toast notifications via winotify."""
import os

try:
    from winotify import Notification
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def notify(title, message, icon_path=None):
    """Show a Windows 10/11 toast. Fails silently if unavailable."""
    if not _AVAILABLE:
        return
    try:
        kwargs = {"app_id": "g-whisper", "title": title, "msg": message}
        if icon_path and os.path.exists(icon_path):
            kwargs["icon"] = os.path.abspath(icon_path)
        n = Notification(**kwargs)
        n.show()
    except Exception:
        pass
