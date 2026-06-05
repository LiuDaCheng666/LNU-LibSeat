"""渐变框 — 8 色标宽谱渐变 + 柔和玻璃反光"""
import weakref

from PySide6.QtCore import Property, QPropertyAnimation, QEasingCurve, Qt, QPointF
from PySide6.QtGui import (
    QLinearGradient, QPainter, QPen, QColor, QPainterPath,
    QRadialGradient, QAction,
)
from PySide6.QtWidgets import QFrame, QMenu
from ..theme import C, RADIUS_LG


# ═══════════════════════════════════
#  配色方案 — 每套 8 色标，色彩丰富，饱和可见
# ═══════════════════════════════════

LIGHT_PALETTES = {
    "aurora": [
        "#c8daf0", "#d4ccf0", "#ccd8f4", "#dcd0f4",
        "#d0d8f0", "#ccc8ec", "#c8d4f0", "#d4ccec",
    ],
    "ocean": [
        "#c0dce8", "#c8d8f0", "#d0ccf0", "#c8d4f4",
        "#c4d8ec", "#ccd0f4", "#c8dcec", "#d0d4f0",
    ],
    "lavender": [
        "#d8c8f0", "#ccd4f4", "#d4ccec", "#c8d8f0",
        "#d0c8ec", "#ccd0f4", "#d8ccf0", "#d0d8f4",
    ],
    "contrast": [
        "#c8dcf4", "#e8ccd8", "#ccd8f0", "#ecd4e0",
        "#d0dcf4", "#e4d0dc", "#cce0f4", "#e8d0d8",
    ],
    "sunset": [
        "#f0d8c8", "#ecd4d0", "#f0dcd0", "#e8d4cc",
        "#ecd8c8", "#f0d4cc", "#e8d8d0", "#f0d8c4",
    ],
}

DARK_PALETTES = {
    "aurora": [
        "#182440", "#201c44", "#1c2244", "#241e42",
        "#1e2442", "#201e40", "#1c2640", "#222040",
    ],
    "ocean": [
        "#142838", "#182640", "#1c1e3e", "#1a2440",
        "#162a3c", "#1e2040", "#182a3e", "#1c2240",
    ],
    "lavender": [
        "#201c40", "#182440", "#1e1e42", "#1c2642",
        "#221e40", "#1a2240", "#201e42", "#1c2440",
    ],
    "contrast": [
        "#182844", "#2c1a2e", "#1c2642", "#301e32",
        "#1a2842", "#2e1c30", "#1c2844", "#2c1e30",
    ],
    "sunset": [
        "#3a2018", "#342020", "#382420", "#32201c",
        "#362220", "#38201c", "#342420", "#3a221c",
    ],
}

CURRENT_PALETTE = "aurora"
_LOW_ANIMATION_MODE = False
_ANIMATED_FRAMES = weakref.WeakSet()


def set_palette(name: str):
    global CURRENT_PALETTE
    if name in LIGHT_PALETTES:
        CURRENT_PALETTE = name


def cycle_palette():
    keys = list(LIGHT_PALETTES.keys())
    idx = keys.index(CURRENT_PALETTE)
    set_palette(keys[(idx + 1) % len(keys)])
    return CURRENT_PALETTE


def is_low_animation_mode() -> bool:
    return _LOW_ANIMATION_MODE


def set_low_animation_mode(enabled: bool):
    global _LOW_ANIMATION_MODE
    _LOW_ANIMATION_MODE = bool(enabled)
    for frame in list(_ANIMATED_FRAMES):
        try:
            frame._sync_animation_state()
        except RuntimeError:
            pass


def _palette_colors():
    from ..theme import current_theme
    palettes = DARK_PALETTES if current_theme() == "dark" else LIGHT_PALETTES
    return palettes.get(CURRENT_PALETTE, palettes["aurora"])


# ═══════════════════════════════════
#  AnimatedGradientFrame
# ═══════════════════════════════════

class AnimatedGradientFrame(QFrame):
    """渐变框。

    8 色标对角渐变高速漂移 + 柔和玻璃高光。
    右键切换配色：极光 / 海洋 / 薰衣草 / 对比 / 日落
    """

    def __init__(self, accent_side="left", parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._accent_side = accent_side
        _ANIMATED_FRAMES.add(self)

        self._anim = QPropertyAnimation(self, b"phase")
        self._anim.setDuration(7200)  # 7.2 秒，比之前快 ~35%
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()
        self._sync_animation_state()

    def get_phase(self): return self._phase
    def set_phase(self, v): self._phase = v; self.update()
    phase = Property(float, get_phase, set_phase)

    def _sync_animation_state(self):
        if _LOW_ANIMATION_MODE or not self.isVisible():
            if self._anim.state() == QPropertyAnimation.State.Running:
                self._anim.pause()
            return

        if self._anim.state() == QPropertyAnimation.State.Stopped:
            self._anim.start()
        elif self._anim.state() == QPropertyAnimation.State.Paused:
            self._anim.resume()

    def showEvent(self, e):
        super().showEvent(e)
        self._sync_animation_state()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._anim.pause()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setFont(self.font())
        menu.setStyleSheet(f"""
            QMenu {{ background: {C.INPUT}; color: {C.TEXT};
                     border: 1px solid {C.BORDER}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 28px 6px 16px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C.ACCENT_SOFT}; }}
        """)
        labels = {"aurora": "🌌  极光（蓝紫）", "ocean": "🌊  海洋（青蓝紫）",
                  "lavender": "💜  薰衣草（紫蓝）", "contrast": "🎭  对比（冷暖）",
                  "sunset": "🌅  日落（暖调）"}
        for key in LIGHT_PALETTES:
            a = QAction(labels.get(key, key), menu)
            a.setCheckable(True)
            a.setChecked(key == CURRENT_PALETTE)
            a.triggered.connect(lambda checked, k=key: self._switch(k))
            menu.addAction(a)
        menu.exec(event.globalPos())

    def _switch(self, name):
        set_palette(name)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 6 or h < 6: p.end(); return
        r = RADIUS_LG
        ph = self._phase

        clip = QPainterPath()
        clip.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), r, r)
        p.setClipPath(clip)

        # ── 8 色标对角渐变 ──
        colors = _palette_colors()
        n = len(colors)  # 8
        grad = QLinearGradient(-w * 0.2, -h * 0.3, w * 1.2, h * 1.3)
        for i, hex_str in enumerate(colors):
            pos = ((i / n) + ph) % 1.0
            grad.setColorAt(pos, QColor(hex_str))
        p.fillRect(self.rect(), grad)

        # ── 柔和玻璃高光 ──
        refl = QLinearGradient(w * 0.02, h * 0.02, w * 0.70, h * 0.80)
        shift = (ph - 0.5) * 0.08
        refl.setColorAt(0.00, QColor(255, 255, 255, 36))
        refl.setColorAt(0.20 + shift, QColor(255, 255, 255, 14))
        refl.setColorAt(0.55 + shift, QColor(255, 255, 255, 3))
        refl.setColorAt(1.00, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), refl)

        spot = QRadialGradient(QPointF(w * 0.82, h * 0.82), min(w, h) * 0.28)
        sa = int(12 + 6 * (1 - abs(ph - 0.5) * 2))
        spot.setColorAt(0.0, QColor(255, 255, 255, sa))
        spot.setColorAt(0.6, QColor(255, 255, 255, sa // 3))
        spot.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), spot)

        p.setClipping(False)

        if self._accent_side == "left":
            bar_h = int(h * 0.7)
            bar_y = (h - bar_h) // 2
            p.fillRect(0, bar_y, 3, bar_h, QColor(C.ACCENT))

        p.setPen(QPen(QColor(C.BORDER_ACCENT), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), r, r)
        p.end()
