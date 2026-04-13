"""Icon art: clean microphone silhouette drawn with PIL.

We render at 4x size then downsample for smooth edges (poor-man's anti-aliasing).
"""
import os

from PIL import Image, ImageDraw


STATUS_COLORS = {
    "loading": (255, 200, 0),
    "idle": (90, 90, 90),
    "recording": (220, 30, 30),
    "transcribing": (30, 120, 220),
    "done": (67, 160, 71),
    "hands_free_listening": (67, 160, 71),
}


def _draw_mic(draw, cx, cy, color, size=64):
    """Draw a clean microphone at (cx, cy). `size` = overall diameter."""
    # Capsule body (rounded rectangle — as two circles + rectangle)
    cap_w = size * 0.32
    cap_h = size * 0.48
    cap_top = cy - cap_h / 2 - size * 0.05
    cap_bot = cap_top + cap_h
    cap_left = cx - cap_w / 2
    cap_right = cx + cap_w / 2
    r = cap_w / 2
    # Top cap
    draw.ellipse(
        (cap_left, cap_top, cap_right, cap_top + cap_w),
        fill=color,
    )
    # Bottom cap
    draw.ellipse(
        (cap_left, cap_bot - cap_w, cap_right, cap_bot),
        fill=color,
    )
    # Middle
    draw.rectangle(
        (cap_left, cap_top + r, cap_right, cap_bot - r),
        fill=color,
    )
    # Horseshoe arc (mic stand arch)
    arc_w = size * 0.52
    arc_left = cx - arc_w / 2
    arc_right = cx + arc_w / 2
    arc_top = cy - arc_w / 2 + size * 0.05
    arc_bot = cy + arc_w / 2 + size * 0.05
    draw.arc(
        (arc_left, arc_top, arc_right, arc_bot),
        start=30, end=150,
        fill=color,
        width=int(size * 0.055),
    )
    # Stem
    stem_top = cap_bot + size * 0.02
    stem_bot = cy + size * 0.3
    stem_w = int(size * 0.055)
    draw.rectangle(
        (cx - stem_w / 2, stem_top, cx + stem_w / 2, stem_bot),
        fill=color,
    )
    # Base
    base_w = size * 0.28
    base_h = size * 0.05
    draw.rectangle(
        (cx - base_w / 2, stem_bot, cx + base_w / 2, stem_bot + base_h),
        fill=color,
    )


def make_tray_icon(bg_color, size=64):
    """Tray icon: colored circle background + white mic silhouette."""
    scale = 4
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Circle background
    draw.ellipse(
        (scale * 2, scale * 2, big - scale * 2, big - scale * 2),
        fill=bg_color + (255,),
        outline=(20, 20, 20, 255),
        width=scale,
    )
    # White mic on top
    _draw_mic(draw, big // 2, big // 2, (255, 255, 255, 240), size=big)
    return img.resize((size, size), Image.LANCZOS)


def make_mono_mic(color=(255, 255, 255, 240), size=64):
    """Transparent background, just the mic silhouette."""
    scale = 4
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _draw_mic(draw, big // 2, big // 2, color, size=big)
    return img.resize((size, size), Image.LANCZOS)


def make_ico_file(path, base_color=(40, 40, 50)):
    """Multi-resolution .ico file for Windows Explorer / shortcuts."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_tray_icon(base_color, s) for s in sizes]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    images[0].save(path, format="ICO", sizes=[(s, s) for s in sizes])


ICONS = {status: make_tray_icon(color) for status, color in STATUS_COLORS.items()}
