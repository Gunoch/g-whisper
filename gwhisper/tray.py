"""System tray UI for g-whisper."""
import os
import sys
import threading

from PIL import Image, ImageDraw
import pystray

from gwhisper.app import GWhisperApp


STATUS_COLORS = {
    "loading": (255, 200, 0),       # amarelo
    "idle": (90, 90, 90),           # cinza
    "recording": (220, 30, 30),     # vermelho
    "transcribing": (30, 120, 220), # azul
    "hands_free_listening": (30, 180, 80),  # verde
}

STATUS_LABELS = {
    "loading": "Carregando...",
    "idle": "Pronto",
    "recording": "Gravando",
    "transcribing": "Transcrevendo",
    "hands_free_listening": "Hands-free (ouvindo)",
}


def _make_icon(color):
    """Generate a 64x64 circle icon with the given color."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color + (255,), outline=(20, 20, 20, 255), width=2)
    # Pequeno "mic" no meio
    draw.rectangle((28, 18, 36, 38), fill=(255, 255, 255, 230))
    draw.ellipse((28, 14, 36, 22), fill=(255, 255, 255, 230))
    draw.ellipse((28, 34, 36, 42), fill=(255, 255, 255, 230))
    draw.rectangle((31, 42, 33, 50), fill=(255, 255, 255, 230))
    draw.rectangle((22, 49, 42, 51), fill=(255, 255, 255, 230))
    return img


ICONS = {status: _make_icon(color) for status, color in STATUS_COLORS.items()}


class TrayUI:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.icon = None
        self.app = None

    def _status_callback(self, status, mode):
        """Called by GWhisperApp when its status changes."""
        if status == "idle" and mode == "hands_free":
            status = "hands_free_listening"
        label = STATUS_LABELS.get(status, status)
        mode_label = "push-to-talk" if mode == "push_to_talk" else "hands-free"
        if self.icon is not None:
            self.icon.icon = ICONS.get(status, ICONS["idle"])
            self.icon.title = f"g-whisper: {label} ({mode_label})"

    def _on_toggle_mode(self, icon, item):
        if self.app:
            self.app._on_toggle_mode()

    def _on_quit(self, icon, item):
        if self.app:
            try:
                self.app._stop_hands_free() if self.app.mode == "hands_free" else None
                self.app.hotkeys.cleanup()
            except Exception:
                pass
        if self.icon:
            self.icon.stop()
        os._exit(0)

    def _setup(self, icon):
        """Called by pystray after the icon thread is ready."""
        icon.visible = True
        try:
            self.app = GWhisperApp(
                config_path=self.config_path,
                status_callback=self._status_callback,
            )
            self.app.start()
        except Exception as e:
            icon.title = f"g-whisper: erro -- {e}"
            print(f"[!] Falha ao iniciar app: {e}")
            raise

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem(
                lambda item: f"Modo: {'hands-free' if self.app and self.app.mode == 'hands_free' else 'push-to-talk'}",
                self._on_toggle_mode,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", self._on_quit),
        )
        self.icon = pystray.Icon(
            "g-whisper",
            icon=ICONS["loading"],
            title="g-whisper: Carregando...",
            menu=menu,
        )
        self.icon.run(setup=self._setup)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    if len(sys.argv) > 1 and not os.path.exists(config_path):
        print(f"[!] Config não encontrada: {config_path}")
        sys.exit(1)
    ui = TrayUI(config_path)
    ui.run()


if __name__ == "__main__":
    main()
