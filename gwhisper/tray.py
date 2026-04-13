"""System tray + floating overlay UI for g-whisper (PyQt6 version)."""
import os
import sys
import threading

import pyperclip
import pystray
import sounddevice as sd
from PyQt6.QtWidgets import QApplication

from gwhisper.app import GWhisperApp
from gwhisper.overlay import RecordingOverlay
from gwhisper.icon_art import ICONS, make_ico_file
from gwhisper import single_instance, startup, notify


STATUS_LABELS = {
    "loading": "Carregando...",
    "idle": "Pronto",
    "recording": "Gravando",
    "transcribing": "Transcrevendo",
    "done": "Pronto",
    "hands_free_listening": "Hands-free (ouvindo)",
}

ICON_PATH = os.path.join("assets", "icon.ico")
LAUNCHER_BAT = "g-whisper.bat"


def _list_input_devices():
    try:
        devices = sd.query_devices()
        return [
            (i, d["name"])
            for i, d in enumerate(devices)
            if d["max_input_channels"] > 0
        ]
    except Exception:
        return []


class TrayUI:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.qt_app = None
        self.icon = None
        self.app = None
        self.overlay = None
        self._current_device = None

    # -- callbacks from app --

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

    def _level_callback(self, level):
        if self.overlay is not None:
            self.overlay.set_level(level)

    def _on_overlay_click(self):
        if self.app:
            self.app.cancel_recording()

    # -- tray menu actions --

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
        if self.qt_app:
            self.qt_app.quit()
        os._exit(0)

    def _on_toggle_startup(self, icon, item):
        if startup.is_enabled():
            startup.disable()
            notify.notify("g-whisper", "Não iniciará mais com o Windows", ICON_PATH)
        else:
            ok = startup.enable(LAUNCHER_BAT, icon_ico=ICON_PATH)
            if ok:
                notify.notify("g-whisper", "Iniciará com o Windows", ICON_PATH)
            else:
                notify.notify("g-whisper", "Falha ao criar atalho de inicialização", ICON_PATH)
        if self.icon:
            self.icon.update_menu()

    def _on_select_device(self, device_index):
        def handler(icon, item):
            if self.app:
                self.app.audio.set_device(device_index)
                self._current_device = device_index
                name = dict(_list_input_devices()).get(device_index, "?")
                notify.notify("g-whisper", f"Microfone: {name[:40]}", ICON_PATH)
                if self.icon:
                    self.icon.update_menu()
        return handler

    def _on_history_copy(self, text):
        def handler(icon, item):
            try:
                pyperclip.copy(text)
                notify.notify("g-whisper", f"Copiado: {text[:50]}", ICON_PATH)
            except Exception as e:
                notify.notify("g-whisper", f"Erro ao copiar: {e}", ICON_PATH)
        return handler

    # -- menu construction --

    def _startup_checked(self, item):
        return startup.is_enabled()

    def _device_checked(self, device_index):
        def check(item):
            return self._current_device == device_index
        return check

    def _build_device_submenu(self):
        items = []
        for idx, name in _list_input_devices():
            label = name[:40]
            items.append(
                pystray.MenuItem(
                    label,
                    self._on_select_device(idx),
                    checked=self._device_checked(idx),
                    radio=True,
                )
            )
        if not items:
            items.append(pystray.MenuItem("(nenhum dispositivo)", None, enabled=False))
        return pystray.Menu(*items)

    def _build_history_submenu(self):
        if not self.app or not self.app.history:
            return pystray.Menu(pystray.MenuItem("(vazio)", None, enabled=False))
        items = []
        for ts, text in list(self.app.history):
            label = text[:50] + ("…" if len(text) > 50 else "")
            items.append(pystray.MenuItem(label, self._on_history_copy(text)))
        return pystray.Menu(*items)

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: (
                    f"Modo: {'hands-free' if self.app and self.app.mode == 'hands_free' else 'push-to-talk'}"
                ),
                self._on_toggle_mode,
            ),
            pystray.MenuItem("Microfone", self._build_device_submenu()),
            pystray.MenuItem("Histórico", self._build_history_submenu()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Iniciar com Windows",
                self._on_toggle_startup,
                checked=self._startup_checked,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", self._on_quit),
        )

    def _init_app(self):
        try:
            self.app = GWhisperApp(
                config_path=self.config_path,
                status_callback=self._status_callback,
                level_callback=self._level_callback,
            )
            self._current_device = self.app.audio.device
            self.app.start()
            if self.icon:
                self.icon.menu = self._build_menu()
                self.icon.update_menu()
        except Exception as e:
            print(f"[!] Falha ao iniciar app: {e}")
            notify.notify("g-whisper", f"Falha ao iniciar: {e}", ICON_PATH)
            if self.overlay:
                self.overlay.show("error", text=str(e)[:40])

    def run(self):
        if not os.path.exists(ICON_PATH):
            try:
                make_ico_file(ICON_PATH)
            except Exception as e:
                print(f"[!] Erro ao gerar .ico: {e}")

        # Qt application on main thread
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        # Overlay widget (created on main thread, controlled via signals)
        self.overlay = RecordingOverlay(on_click=self._on_overlay_click)

        # Tray icon in detached thread
        self.icon = pystray.Icon(
            "g-whisper",
            icon=ICONS["loading"],
            title="g-whisper: Carregando...",
            menu=self._build_menu(),
        )
        self.icon.run_detached()

        # App initialization in background
        threading.Thread(target=self._init_app, daemon=True).start()

        # Block on Qt event loop
        try:
            self.qt_app.exec()
        except KeyboardInterrupt:
            self._on_quit(None, None)


def main():
    lock = single_instance.SingleInstance()
    if not lock.acquire():
        notify.notify("g-whisper", "Já está em execução (ícone na bandeja)", ICON_PATH)
        sys.exit(0)

    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    if len(sys.argv) > 1 and not os.path.exists(config_path):
        print(f"[!] Config não encontrada: {config_path}")
        sys.exit(1)
    ui = TrayUI(config_path)
    try:
        ui.run()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
