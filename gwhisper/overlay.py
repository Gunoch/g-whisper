"""Floating recording overlay (Wispr Flow style).

Translucent pill at the bottom of the screen that shows live status:
  - Recording: 5 animated level bars reacting to mic volume
  - Transcribing: pulsing blue dot + "Transcrevendo..."
  - Done: green check + last transcription text (2s, auto-hide)
  - Click anywhere on the pill to cancel current recording

All widget operations happen on the Tk main thread via a command queue
that is polled every 50ms. External threads call `show()` / `hide()` /
`set_level()` which are thread-safe (queue.put).
"""
import queue
import tkinter as tk


PILL_WIDTH = 300
PILL_HEIGHT = 56
MARGIN_BOTTOM = 80
BG_COLOR = "#1a1a1a"
TEXT_COLOR = "#f0f0f0"
TRANSPARENT_KEY = "magenta"
NUM_BARS = 5
BAR_WIDTH = 4
BAR_GAP = 4
BAR_MAX_H = 28

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
    def __init__(self, root, on_click=None):
        self.root = root
        self.queue = queue.Queue()
        self.on_click = on_click

        self._pulse_after_id = None
        self._auto_hide_after_id = None
        self._fade_after_id = None
        self._level_decay_after_id = None
        self._level = 0.0
        self._bars_state = [0.0] * NUM_BARS
        self._current_status = None

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass
        self.window.attributes("-alpha", 0.0)
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
            cursor="hand2",
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._handle_click)

        self._draw_pill_background()

        # Status indicator (circle, shown for non-recording states)
        self.dot = self.canvas.create_oval(
            22, PILL_HEIGHT // 2 - 7, 36, PILL_HEIGHT // 2 + 7,
            fill="#888", outline="",
        )

        # Level bars (shown during recording/hands-free)
        self.bars = []
        bars_cx = 29
        bars_total_w = NUM_BARS * BAR_WIDTH + (NUM_BARS - 1) * BAR_GAP
        bars_left = bars_cx - bars_total_w // 2
        for i in range(NUM_BARS):
            bx = bars_left + i * (BAR_WIDTH + BAR_GAP)
            bar = self.canvas.create_rectangle(
                bx, PILL_HEIGHT // 2,
                bx + BAR_WIDTH, PILL_HEIGHT // 2,
                fill="#e53935", outline="", state="hidden",
            )
            self.bars.append(bar)

        self.text_id = self.canvas.create_text(
            60, PILL_HEIGHT // 2,
            text="",
            fill=TEXT_COLOR,
            font=("Segoe UI", 11),
            anchor="w",
        )

        self.window.withdraw()
        self.root.after(50, self._poll)
        self.root.after(40, self._animate_bars)

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

    # -- thread-safe API --

    def show(self, status, text=""):
        self.queue.put(("show", status, text))

    def hide(self):
        self.queue.put(("hide",))

    def set_level(self, level):
        """Audio level 0.0-1.0, called from audio thread."""
        self._level = max(0.0, min(1.0, float(level)))

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
        self._current_status = status
        color = STATUS_COLORS.get(status, "#888")
        label = STATUS_LABELS.get(status, status)

        if status == "done" and text:
            label = self._truncate(text, 38)

        self.canvas.itemconfig(self.text_id, text=label)

        if status in ("recording", "hands_free"):
            self.canvas.itemconfig(self.dot, state="hidden")
            for bar in self.bars:
                self.canvas.itemconfig(bar, fill=color, state="normal")
            self._stop_pulse()
        else:
            for bar in self.bars:
                self.canvas.itemconfig(bar, state="hidden")
            self.canvas.itemconfig(self.dot, state="normal", fill=color)
            if status == "transcribing":
                self._start_pulse()
            else:
                self._stop_pulse()

        self.window.deiconify()
        self.window.lift()
        self._fade_to(0.95)

        if status == "done":
            self._auto_hide_after_id = self.root.after(2000, self._apply_hide)

    def _apply_hide(self):
        self._cancel_auto_hide()
        self._stop_pulse()
        self._current_status = None
        self._fade_to(0.0, then=self.window.withdraw)

    def _apply_destroy(self):
        self._cancel_auto_hide()
        self._stop_pulse()
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    # -- fade animation --

    def _fade_to(self, target, step=0.15, then=None):
        if self._fade_after_id:
            self.root.after_cancel(self._fade_after_id)
            self._fade_after_id = None

        def tick():
            try:
                current = float(self.window.attributes("-alpha"))
            except tk.TclError:
                return
            if abs(current - target) < step:
                self.window.attributes("-alpha", target)
                self._fade_after_id = None
                if then:
                    then()
                return
            new = current + (step if target > current else -step)
            self.window.attributes("-alpha", new)
            self._fade_after_id = self.root.after(16, tick)

        tick()

    # -- pulsing dot (transcribing) --

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

    # -- level bars animation --

    def _animate_bars(self):
        """Update bar heights from self._level with decay and per-bar randomness."""
        if self._current_status in ("recording", "hands_free"):
            # Each bar gets a slightly different portion of the level
            # to look more organic
            import random
            for i, bar in enumerate(self.bars):
                target = self._level * (0.6 + 0.4 * random.random())
                self._bars_state[i] = max(
                    self._bars_state[i] * 0.7,  # decay
                    target,
                )
                h = max(3, self._bars_state[i] * BAR_MAX_H)
                bars_cx = 29
                bars_total_w = NUM_BARS * BAR_WIDTH + (NUM_BARS - 1) * BAR_GAP
                bars_left = bars_cx - bars_total_w // 2
                bx = bars_left + i * (BAR_WIDTH + BAR_GAP)
                y_center = PILL_HEIGHT // 2
                self.canvas.coords(
                    bar,
                    bx, y_center - h / 2,
                    bx + BAR_WIDTH, y_center + h / 2,
                )
            # Decay the level input toward 0 so bars settle if no updates
            self._level *= 0.9
        self.root.after(40, self._animate_bars)

    def _cancel_auto_hide(self):
        if self._auto_hide_after_id:
            self.root.after_cancel(self._auto_hide_after_id)
            self._auto_hide_after_id = None

    def _handle_click(self, event):
        if self.on_click and self._current_status in ("recording", "hands_free"):
            self.on_click()

    @staticmethod
    def _truncate(text, max_len):
        return text if len(text) <= max_len else text[: max_len - 1] + "…"
