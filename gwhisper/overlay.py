"""Floating recording overlay (Wispr Flow / Raycast style) with PyQt6.

Uses Windows 11 DWM Acrylic backdrop for real glassmorphism, plus Qt's
native signal/slot system for thread-safe updates from the audio thread.

States:
  - recording: 5 animated level bars driven by mic RMS
  - transcribing: pulsing dot
  - done: green check + transcribed text (auto-hides after 2s)
  - hands_free: level bars in green, "Ouvindo"
  - loading, error
"""
import ctypes
import ctypes.wintypes
import random
import sys

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject,
    QRect,
)
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QBrush, QFont, QFontDatabase, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGraphicsDropShadowEffect,
)


PILL_WIDTH = 300
PILL_HEIGHT = 56
MARGIN_BOTTOM = 80
CONTAINER_PADDING = 40
WINDOW_WIDTH = PILL_WIDTH + CONTAINER_PADDING * 2
WINDOW_HEIGHT = PILL_HEIGHT + CONTAINER_PADDING * 2

ACCENTS = {
    "recording": QColor("#e53935"),
    "transcribing": QColor("#1e88e5"),
    "hands_free": QColor("#43a047"),
    "done": QColor("#43a047"),
    "loading": QColor("#fdd835"),
    "error": QColor("#ef6c00"),
}

LABELS = {
    "recording": "Gravando",
    "transcribing": "Transcrevendo…",
    "hands_free": "Ouvindo",
    "done": "",
    "loading": "Carregando modelo…",
    "error": "Erro",
}

PILL_BG = QColor(26, 26, 26, 235)
TEXT_COLOR = QColor(240, 240, 240)


def _enable_acrylic(hwnd):
    """Apply Windows 11 DWM Acrylic backdrop to the given HWND.

    Safe no-op on older Windows versions or if the call fails.
    """
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        # DWMWA_SYSTEMBACKDROP_TYPE = 38 (Windows 11 22H2+)
        # DWMSBT_TRANSIENTWINDOW = 3 (Acrylic)
        value = ctypes.c_int(3)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd), 38, ctypes.byref(value), ctypes.sizeof(value)
        )
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33
        # DWMWCP_ROUND = 2
        round_pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd), 33, ctypes.byref(round_pref), ctypes.sizeof(round_pref)
        )
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd), 20, ctypes.byref(dark), ctypes.sizeof(dark)
        )
    except Exception:
        pass


class _Bridge(QObject):
    """Thread-safe bridge: audio-thread callers emit signals, which Qt
    delivers to slots on the UI thread."""
    show_signal = pyqtSignal(str, str)
    hide_signal = pyqtSignal()
    level_signal = pyqtSignal(float)
    destroy_signal = pyqtSignal()


class PillWidget(QWidget):
    def __init__(self, on_click=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            if False
            else Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowOpacity(0.0)

        self._status = "idle"
        self._label_text = ""
        self._accent = ACCENTS["hands_free"]
        self._level = 0.0
        self._bars = [0.0] * 5
        self._pulse_phase = 0.0
        self._on_click = on_click

        # Drop shadow via graphics effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

        # Fade animation
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(250)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Animation tick (level decay + pulse + repaint)
        self._tick = QTimer(self)
        self._tick.setInterval(33)  # ~30fps
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        # Auto-hide timer
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self.hide_overlay)

        # Position at bottom-center of primary screen
        self._position_on_screen()

        # Font: Inter if available, else Segoe UI Variable, else fallback
        self._font = QFont()
        for family in ("Inter", "Segoe UI Variable", "Segoe UI", "Arial"):
            if family in QFontDatabase.families():
                self._font.setFamily(family)
                break
        self._font.setPixelSize(14)
        self._font.setWeight(QFont.Weight.Medium)
        self._font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)

    def showEvent(self, event):
        super().showEvent(event)
        # Apply acrylic after window has native HWND
        hwnd = int(self.winId())
        _enable_acrylic(hwnd)

    def _position_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - WINDOW_WIDTH) // 2
        y = screen.height() - WINDOW_HEIGHT - MARGIN_BOTTOM + CONTAINER_PADDING
        self.move(x, y)

    # -- slots (main thread) --

    def show_state(self, status, text=""):
        self._auto_hide.stop()
        self._status = status
        self._label_text = LABELS.get(status, "") if status != "done" else text
        self._accent = ACCENTS.get(status, QColor("#888888"))
        if not self.isVisible():
            self.show()
            self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()
        if status == "done":
            self._auto_hide.start(2000)
        self.update()

    def hide_overlay(self):
        self._auto_hide.stop()
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)

        def on_finished():
            if self.windowOpacity() <= 0.01:
                self.hide()
                self._status = "idle"

        try:
            self._fade.finished.disconnect()
        except TypeError:
            pass
        self._fade.finished.connect(on_finished)
        self._fade.start()

    def set_level(self, level):
        self._level = max(0.0, min(1.0, float(level)))

    # -- animation tick --

    def _on_tick(self):
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

        # Pill rectangle centered in the padded window
        pill_rect = QRect(
            CONTAINER_PADDING, CONTAINER_PADDING,
            PILL_WIDTH, PILL_HEIGHT,
        )

        # Glass pill background with subtle border
        path = QPainterPath()
        path.addRoundedRect(
            pill_rect.x(), pill_rect.y(), pill_rect.width(), pill_rect.height(),
            PILL_HEIGHT / 2, PILL_HEIGHT / 2,
        )
        p.fillPath(path, QBrush(PILL_BG))

        # Hairline border
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Left indicator
        indicator_rect = QRect(
            pill_rect.x() + 20, pill_rect.y() + 10,
            40, PILL_HEIGHT - 20,
        )
        self._paint_indicator(p, indicator_rect)

        # Label
        p.setFont(self._font)
        p.setPen(QPen(TEXT_COLOR))
        label_rect = QRect(
            indicator_rect.right() + 10, pill_rect.y(),
            pill_rect.width() - indicator_rect.width() - 50, pill_rect.height(),
        )
        align = Qt.AlignmentFlag.AlignVCenter
        if self._status == "done":
            align |= Qt.AlignmentFlag.AlignLeft
            text = self._label_text or ""
            # elide if too long
            metrics = p.fontMetrics()
            text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, label_rect.width())
        else:
            align |= Qt.AlignmentFlag.AlignRight
            text = self._label_text
        p.drawText(label_rect, align, text)

    def _paint_indicator(self, p, rect):
        if self._status in ("recording", "hands_free"):
            self._paint_bars(p, rect)
        elif self._status in ("transcribing", "loading", "error"):
            self._paint_dot(p, rect)
        elif self._status == "done":
            self._paint_check(p, rect)

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
        # Pulsing dot
        import math
        pulse = 0.7 + 0.3 * math.sin(self._pulse_phase * math.tau)
        size = int(12 * pulse)
        cx, cy = rect.center().x(), rect.center().y()
        # Halo glow
        glow = QColor(self._accent)
        glow.setAlpha(80)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(cx - size - 4, cy - size - 4, (size + 4) * 2, (size + 4) * 2)
        # Dot
        p.setBrush(QBrush(self._accent))
        p.drawEllipse(cx - size, cy - size, size * 2, size * 2)

    def _paint_check(self, p, rect):
        cx, cy = rect.center().x(), rect.center().y()
        # Filled circle
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._accent))
        p.drawEllipse(cx - 12, cy - 12, 24, 24)
        # Check mark
        pen = QPen(QColor(255, 255, 255), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(cx - 5, cy, cx - 1, cy + 4)
        p.drawLine(cx - 1, cy + 4, cx + 6, cy - 4)

    def mousePressEvent(self, event):
        if self._status in ("recording", "hands_free") and self._on_click:
            self._on_click()


class RecordingOverlay:
    """Thread-safe facade. Construct on the UI thread; call show/hide/set_level
    from any thread."""

    def __init__(self, on_click=None):
        self._bridge = _Bridge()
        self._pill = PillWidget(on_click=on_click)
        self._bridge.show_signal.connect(self._pill.show_state)
        self._bridge.hide_signal.connect(self._pill.hide_overlay)
        self._bridge.level_signal.connect(self._pill.set_level)
        self._bridge.destroy_signal.connect(self._pill.close)

    def show(self, status, text=""):
        self._bridge.show_signal.emit(status, text)

    def hide(self):
        self._bridge.hide_signal.emit()

    def set_level(self, level):
        self._bridge.level_signal.emit(float(level))

    def destroy(self):
        self._bridge.destroy_signal.emit()
