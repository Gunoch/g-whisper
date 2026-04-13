"""Always-visible floating pill (Wispr Flow / Raycast style) with PyQt6.

The pill stays at the bottom of the screen at all times. Click it to
start/stop recording (toggle), or use F9 hotkey. Drag to reposition;
position is remembered via QSettings.

States:
  - idle: dim pill, mic icon + "Pronto" hint (clickable to start)
  - hover: idle pill brightens
  - recording: red, 5 animated level bars
  - transcribing: blue pulsing dot
  - done: green check + transcribed text (2s → returns to idle)
  - hands_free: green, level bars, "Ouvindo"
  - loading, error
"""
import ctypes
import ctypes.wintypes
import math
import random

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject,
    QRect, QPoint, QSettings,
)
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QFont, QFontDatabase, QPen, QCursor,
)
from PyQt6.QtWidgets import QApplication, QWidget


PILL_WIDTH = 300
PILL_HEIGHT = 56
DEFAULT_MARGIN_BOTTOM = 80

ACCENTS = {
    "idle": QColor("#666666"),
    "recording": QColor("#e53935"),
    "transcribing": QColor("#1e88e5"),
    "hands_free": QColor("#43a047"),
    "done": QColor("#43a047"),
    "loading": QColor("#fdd835"),
    "error": QColor("#ef6c00"),
}

LABELS = {
    "idle": "F9 ou clique para gravar",
    "recording": "Gravando",
    "transcribing": "Transcrevendo…",
    "hands_free": "Ouvindo",
    "done": "",
    "loading": "Carregando modelo…",
    "error": "Erro",
}

PILL_BG = QColor(26, 26, 26, 240)
PILL_BG_IDLE = QColor(20, 20, 20, 200)
PILL_BG_HOVER = QColor(35, 35, 35, 240)
TEXT_COLOR = QColor(240, 240, 240)
TEXT_COLOR_DIM = QColor(160, 160, 165)
DRAG_THRESHOLD = 5  # pixels — click vs drag


def _enable_dark_mode(hwnd):
    """Apply DWM immersive dark mode (harmless if Win10/older)."""
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd), 20,
            ctypes.byref(dark), ctypes.sizeof(dark),
        )
    except Exception:
        pass


class _Bridge(QObject):
    show_signal = pyqtSignal(str, str)
    level_signal = pyqtSignal(float)
    destroy_signal = pyqtSignal()


class PillWidget(QWidget):
    def __init__(self, on_click=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(PILL_WIDTH, PILL_HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._status = "idle"
        self._label_text = ""
        self._accent = ACCENTS["idle"]
        self._level = 0.0
        self._bars = [0.0] * 5
        self._pulse_phase = 0.0
        self._on_click = on_click
        self._hover = False
        self._drag_start = None
        self._was_dragging = False

        self._settings = QSettings("g-whisper", "overlay")

        self._tick = QTimer(self)
        self._tick.setInterval(33)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        self._auto_revert = QTimer(self)
        self._auto_revert.setSingleShot(True)
        self._auto_revert.timeout.connect(lambda: self.show_state("idle"))

        self._position_on_screen()
        self._setup_font()

    def _setup_font(self):
        self._font = QFont()
        self._font_idle = QFont()
        for family in ("Inter", "Segoe UI Variable", "Segoe UI", "Arial"):
            if family in QFontDatabase.families():
                self._font.setFamily(family)
                self._font_idle.setFamily(family)
                break
        self._font.setPixelSize(14)
        self._font.setWeight(QFont.Weight.Medium)
        self._font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
        self._font_idle.setPixelSize(12)
        self._font_idle.setWeight(QFont.Weight.Normal)
        self._font_idle.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        _enable_dark_mode(hwnd)

    def _position_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        saved_x = self._settings.value("x", -1, int)
        saved_y = self._settings.value("y", -1, int)
        if saved_x >= 0 and saved_y >= 0:
            x = max(0, min(saved_x, screen.width() - PILL_WIDTH))
            y = max(0, min(saved_y, screen.height() - PILL_HEIGHT))
        else:
            x = (screen.width() - PILL_WIDTH) // 2
            y = screen.height() - PILL_HEIGHT - DEFAULT_MARGIN_BOTTOM
        self.move(x, y)

    # -- slots (UI thread) --

    def show_state(self, status, text=""):
        self._auto_revert.stop()
        self._status = status
        self._label_text = LABELS.get(status, "") if status != "done" else text
        self._accent = ACCENTS.get(status, QColor("#888888"))
        if not self.isVisible():
            self.show()
            self.raise_()
        if status == "done":
            self._auto_revert.start(2200)
        self.update()

    def set_level(self, level):
        self._level = max(0.0, min(1.0, float(level)))

    # -- mouse events --

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.pos()
            self._was_dragging = False

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start:
            new_pos = event.globalPosition().toPoint() - self._drag_start
            delta = (new_pos - self.pos()).manhattanLength()
            if delta > DRAG_THRESHOLD or self._was_dragging:
                self._was_dragging = True
                self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._was_dragging:
            self._settings.setValue("x", self.x())
            self._settings.setValue("y", self.y())
            self._was_dragging = False
            self._drag_start = None
            return
        self._drag_start = None
        if self._on_click:
            try:
                self._on_click(self._status)
            except Exception as e:
                print(f"[overlay] click handler error: {e}")

    # -- animation tick --

    def _on_tick(self):
        if not self.isVisible():
            return
        if self._status in ("recording", "hands_free"):
            for i in range(len(self._bars)):
                target = self._level * (0.55 + 0.45 * random.random())
                self._bars[i] = max(self._bars[i] * 0.75, target)
            self._level *= 0.9
        self._pulse_phase = (self._pulse_phase + 0.04) % 1.0
        self.update()

    # -- paint --

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = PILL_HEIGHT / 2

        if self._status == "idle":
            bg = PILL_BG_HOVER if self._hover else PILL_BG_IDLE
        else:
            bg = PILL_BG

        # Pill-shaped fill (true full-radius round)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(rect, radius, radius)

        # Hairline border
        border_alpha = 35 if self._hover and self._status == "idle" else 22
        p.setPen(QPen(QColor(255, 255, 255, border_alpha), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, radius, radius)

        indicator_rect = QRect(20, 10, 40, PILL_HEIGHT - 20)
        self._paint_indicator(p, indicator_rect)

        # Label
        if self._status == "idle":
            p.setFont(self._font_idle)
            p.setPen(QPen(TEXT_COLOR if self._hover else TEXT_COLOR_DIM))
        else:
            p.setFont(self._font)
            p.setPen(QPen(TEXT_COLOR))

        label_rect = QRect(
            indicator_rect.right() + 10, 0,
            PILL_WIDTH - indicator_rect.right() - 30, PILL_HEIGHT,
        )
        align = Qt.AlignmentFlag.AlignVCenter
        if self._status == "done":
            align |= Qt.AlignmentFlag.AlignLeft
            text = self._label_text or ""
            metrics = p.fontMetrics()
            text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, label_rect.width())
        elif self._status == "idle":
            align |= Qt.AlignmentFlag.AlignRight
            text = self._label_text
        else:
            align |= Qt.AlignmentFlag.AlignRight
            text = self._label_text
        p.drawText(label_rect, align, text)

    def _paint_indicator(self, p, rect):
        if self._status == "idle":
            self._paint_idle_mic(p, rect)
        elif self._status in ("recording", "hands_free"):
            self._paint_bars(p, rect)
        elif self._status in ("transcribing", "loading", "error"):
            self._paint_dot(p, rect)
        elif self._status == "done":
            self._paint_check(p, rect)

    def _paint_idle_mic(self, p, rect):
        # Small white mic icon, dimmer when not hovered
        color = QColor(220, 220, 230) if self._hover else QColor(140, 140, 150)
        cx, cy = rect.center().x(), rect.center().y()
        # Capsule body
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawRoundedRect(cx - 4, cy - 10, 8, 16, 4, 4)
        # Stand arc
        pen = QPen(color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(cx - 8, cy - 4, 16, 14, 200 * 16, 140 * 16)
        # Stem
        p.drawLine(cx, cy + 9, cx, cy + 12)

    def _paint_bars(self, p, rect):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._accent))
        num = len(self._bars)
        bar_w = 4
        gap = 4
        total_w = num * bar_w + (num - 1) * gap
        start_x = rect.x() + (rect.width() - total_w) // 2
        cy = rect.y() + rect.height() / 2
        max_h = rect.height() - 4
        for i, v in enumerate(self._bars):
            h = max(4, v * max_h)
            x = start_x + i * (bar_w + gap)
            y = cy - h / 2
            p.drawRoundedRect(int(x), int(y), bar_w, int(h), 2, 2)

    def _paint_dot(self, p, rect):
        pulse = 0.7 + 0.3 * math.sin(self._pulse_phase * math.tau)
        size = max(4, int(12 * pulse))
        cx, cy = rect.center().x(), rect.center().y()
        glow = QColor(self._accent)
        glow.setAlpha(80)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(cx - size - 4, cy - size - 4, (size + 4) * 2, (size + 4) * 2)
        p.setBrush(QBrush(self._accent))
        p.drawEllipse(cx - size, cy - size, size * 2, size * 2)

    def _paint_check(self, p, rect):
        cx, cy = rect.center().x(), rect.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._accent))
        p.drawEllipse(cx - 12, cy - 12, 24, 24)
        pen = QPen(QColor(255, 255, 255), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(cx - 5, cy, cx - 1, cy + 4)
        p.drawLine(cx - 1, cy + 4, cx + 6, cy - 4)


class RecordingOverlay:
    """Thread-safe facade. Construct on UI thread; call from any thread."""

    def __init__(self, on_click=None):
        self._bridge = _Bridge()
        self._pill = PillWidget(on_click=on_click)
        self._bridge.show_signal.connect(self._pill.show_state)
        self._bridge.level_signal.connect(self._pill.set_level)
        self._bridge.destroy_signal.connect(self._pill.close)
        # Show idle state immediately
        self._pill.show_state("idle")

    def show(self, status, text=""):
        self._bridge.show_signal.emit(status, text)

    def hide(self):
        # In always-visible mode, "hide" means revert to idle
        self._bridge.show_signal.emit("idle", "")

    def set_level(self, level):
        self._bridge.level_signal.emit(float(level))

    def destroy(self):
        self._bridge.destroy_signal.emit()
