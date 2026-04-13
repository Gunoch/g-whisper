import queue
import threading
import keyboard


class HotkeyManager:
    def __init__(self, config):
        cfg = config["hotkeys"]
        self.ptt_key = cfg["push_to_talk"]
        self.quit_key = cfg["quit"]
        self.toggle_key = cfg["toggle_mode"]
        self._action_queue = None
        self._worker_thread = None

    def setup_push_to_talk(self, on_press, on_release):
        self._action_queue = queue.Queue()

        keyboard.on_press_key(
            self.ptt_key,
            lambda e: self._action_queue.put(("press",)),
            suppress=True,
        )
        keyboard.on_release_key(
            self.ptt_key,
            lambda e: self._action_queue.put(("release",)),
            suppress=True,
        )

        def worker():
            pressed = False
            while True:
                action = self._action_queue.get()
                if action[0] == "press" and not pressed:
                    pressed = True
                    on_press()
                elif action[0] == "release" and pressed:
                    pressed = False
                    on_release()
                elif action[0] == "quit":
                    break

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def setup_quit(self, on_quit):
        keyboard.add_hotkey(self.quit_key, on_quit, suppress=True)

    def setup_toggle(self, on_toggle):
        keyboard.add_hotkey(self.toggle_key, on_toggle, suppress=True)

    def wait(self):
        keyboard.wait()

    def cleanup(self):
        if self._action_queue:
            self._action_queue.put(("quit",))
        keyboard.unhook_all()
