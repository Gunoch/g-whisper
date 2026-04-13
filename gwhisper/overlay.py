"""Floating recording overlay (Wispr Flow style).

A small translucent pill at the bottom-center of the screen showing
status (recording, transcribing, done) with an animated colored dot.
"""
import queue
import tkinter as tk


PILL_WIDTH = 280
PILL_HEIGHT = 56
MARGIN_BOTTOM = 80
BG_COLOR = "#1a1a1a"
TEXT_COLOR = "#f0f0f0"
TRANSPARENT_KEY = "magenta"

STATUS_COLORS = {
    "loading": "#fdd835",
    "recording": "#e53935",
    "transcribing": "#1e88e5",
    "hands_free": "#43a047",
    "done": "#43a047",
    "error": "#ef6c00",
}

STATUS_LABELS = {
    "loading": "Carregando modelo...",
    "recording": "Gravando",
    "transcribing": "Transcrevendo...",
    "hands_free": "Ouvindo",
    "done": "",
    "error": "Erro",
}


class RecordingOverlay:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self._pulse_after_id = None
        self._auto_hide_after_id = None

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass
        self.window.attributes("-alpha", 0.95)
        self.window.configure(bg=TRANSPARENT_KEY)

        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = (screen_w - PILL_WIDTH) // 2
        y = screen_h - PILL_HEIGHT - MARGIN_BOTTOM
        self.window.geometry(f"{PILL_WIDTH}x{PILL_HEIGHT}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.window,
            width=PILL_WIDTH,
            height=PILL_HEIGHT,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.pack()
        self._draw_pill_background()

        self.dot = self.canvas.create_oval(
            22, PILL_HEIGHT // 2 - 7, 36, PILL_HEIGHT // 2 + 7,
            fill="#888", outline="",
        )
        self.text_id = self.canvas.create_text(
            52, PILL_HEIGHT // 2,
            text="",
            fill=TEXT_COLOR,
            font=("Segoe UI", 11),
            anchor="w",
        )

        self.window.withdraw()
        self.root.after(50, self._poll)

    def _draw_pill_background(self):
        r = PILL_HEIGHT // 2
        self.canvas.create_oval(0, 0, 2 * r, PILL_HEIGHT, fill=BG_COLOR, outline="")
        self.canvas.create_oval(
            PILL_WIDTH - 2 * r, 0, PILL_WIDTH, PILL_HEIGHT,
            fill=BG_COLOR, outline="",
        )
        self.canvas.create_rectangle(
            r, 0, PILL_WIDTH - r, PILL_HEIGHT,
            fill=BG_COLOR, outline="",
        )

    # -- public thread-safe API --

    def show(self, status, text=""):
        self.queue.put(("show", status, text))

    def hide(self):
        self.queue.put(("hide",))

    def destroy(self):
        self.queue.put(("destroy",))

    # -- main thread handlers --

    def _poll(self):
        try:
            while True:
                cmd = self.queue.get_nowait()
                action = cmd[0]
                if action == "show":
                    self._apply_show(cmd[1], cmd[2])
                elif action == "hide":
                    self._apply_hide()
                elif action == "destroy":
                    self._apply_destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _apply_show(self, status, text):
        self._cancel_auto_hide()
        color = STATUS_COLORS.get(status, "#888")
        label = STATUS_LABELS.get(status, status)

        if status == "done" and text:
            label = self._truncate(text, 36)
            color = STATUS_COLORS["done"]

        self.canvas.itemconfig(self.dot, fill=color)
        self.canvas.itemconfig(self.text_id, text=label)
        self.window.deiconify()
        self.window.lift()

        if status in ("recording", "hands_free"):
            self._start_pulse()
        else:
            self._stop_pulse()

        if status == "done":
            self._auto_hide_after_id = self.root.after(2000, self._apply_hide)

    def _apply_hide(self):
        self._cancel_auto_hide()
        self._stop_pulse()
        self.window.withdraw()

    def _apply_destroy(self):
        self._cancel_auto_hide()
        self._stop_pulse()
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def _start_pulse(self):
        self._stop_pulse()
        self._pulse_visible = True
        self._pulse_tick()

    def _pulse_tick(self):
        self._pulse_visible = not self._pulse_visible
        self.canvas.itemconfig(
            self.dot,
            state="normal" if self._pulse_visible else "hidden",
        )
        self._pulse_after_id = self.root.after(500, self._pulse_tick)

    def _stop_pulse(self):
        if self._pulse_after_id:
            self.root.after_cancel(self._pulse_after_id)
            self._pulse_after_id = None
        self.canvas.itemconfig(self.dot, state="normal")

    def _cancel_auto_hide(self):
        if self._auto_hide_after_id:
            self.root.after_cancel(self._auto_hide_after_id)
            self._auto_hide_after_id = None

    @staticmethod
    def _truncate(text, max_len):
        return text if len(text) <= max_len else text[: max_len - 1] + "…"
