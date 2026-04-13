"""System tray + floating overlay UI for g-whisper."""
import os
import sys
import threading
import tkinter as tk

from PIL import Image, ImageDraw
import pystray

from gwhisper.app import GWhisperApp
from gwhisper.overlay import RecordingOverlay


STATUS_COLORS = {
    "loading": (255, 200, 0),
    "idle": (90, 90, 90),
    "recording": (220, 30, 30),
    "transcribing": (30, 120, 220),
    "done": (67, 160, 71),
    "hands_free_listening": (67, 160, 71),
}

STATUS_LABELS = {
    "loading": "Carregando...",
    "idle": "Pronto",
    "recording": "Gravando",
    "transcribing": "Transcrevendo",
    "done": "Pronto",
    "hands_free_listening": "Hands-free (ouvindo)",
}


def _make_icon(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color + (255,), outline=(20, 20, 20, 255), width=2)
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
        self.overlay = None
        self.root = None

    def _status_callback(self, status, mode, text=""):
        icon_status = status
        if status == "idle" and mode == "hands_free":
            icon_status = "hands_free_listening"
        if self.icon is not None:
            self.icon.icon = ICONS.get(icon_status, ICONS["idle"])
            label = STATUS_LABELS.get(icon_status, icon_status)
            mode_label = "push-to-talk" if mode == "push_to_talk" else "hands-free"
            self.icon.title = f"g-whisper: {label} ({mode_label})"

        if self.overlay is not None:
            if status == "loading":
                self.overlay.show("loading")
            elif status == "recording":
                self.overlay.show("recording")
            elif status == "transcribing":
                self.overlay.show("transcribing")
            elif status == "done":
                self.overlay.show("done", text=text)
            elif status == "idle":
                if mode == "hands_free":
                    self.overlay.show("hands_free")
                else:
                    self.overlay.hide()

    def _on_toggle_mode(self, icon, item):
        if self.app:
            self.app._on_toggle_mode()

    def _on_quit(self, icon, item):
        if self.app:
            try:
                if self.app.mode == "hands_free":
                    self.app._stop_hands_free()
                self.app.hotkeys.cleanup()
            except Exception:
                pass
        if self.overlay:
            self.overlay.destroy()
        if self.icon:
            self.icon.stop()
        if self.root:
            try:
                self.root.after(0, self.root.quit)
            except Exception:
                pass
        os._exit(0)

    def _init_app(self):
        try:
            self.app = GWhisperApp(
                config_path=self.config_path,
                status_callback=self._status_callback,
            )
            self.app.start()
        except Exception as e:
            print(f"[!] Falha ao iniciar app: {e}")
            if self.overlay:
                self.overlay.show("error", text=str(e)[:40])

    def run(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.overlay = RecordingOverlay(self.root)

        menu = pystray.Menu(
            pystray.MenuItem(
                lambda item: (
                    f"Modo: {'hands-free' if self.app and self.app.mode == 'hands_free' else 'push-to-talk'}"
                ),
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
        self.icon.run_detached()

        threading.Thread(target=self._init_app, daemon=True).start()

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._on_quit(None, None)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    if len(sys.argv) > 1 and not os.path.exists(config_path):
        print(f"[!] Config não encontrada: {config_path}")
        sys.exit(1)
    ui = TrayUI(config_path)
    ui.run()


if __name__ == "__main__":
    main()
