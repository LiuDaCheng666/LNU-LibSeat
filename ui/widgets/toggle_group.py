"""模式切换 — 分段按钮（渐变激活态 + 按压深度）"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget
from ..theme import C, sans, RADIUS_MD


# 激活态渐变
ACTIVE_GRADIENT = f"""
    qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C.GRADIENT_PURPLE_START},
        stop:1 {C.GRADIENT_BLUE_END})
"""

ACTIVE_HOVER = f"""
    qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C.PURPLE_HOT},
        stop:1 {C.ACCENT_HOT})
"""


class ToggleGroup(QWidget):
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)

        self._btn_multi = QPushButton("≡  多账号分时段")
        self._btn_single = QPushButton("☰  单账号逐段")

        for b in (self._btn_multi, self._btn_single):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(sans(10, bold=True))
            b.setMinimumHeight(40)
            b.setMinimumWidth(150)

        self._btn_multi.clicked.connect(lambda: self._select("multi"))
        self._btn_single.clicked.connect(lambda: self._select("single"))

        l.addWidget(self._btn_multi)
        l.addWidget(self._btn_single)
        l.addStretch(1)

        self._mode = "multi"
        self._refresh()

    def mode(self):
        return self._mode

    def _select(self, mode):
        if mode == self._mode:
            return
        self._mode = mode
        self._refresh()
        self.mode_changed.emit(mode)

    def set_mode(self, mode):
        if mode not in ("multi", "single") or mode == self._mode:
            return
        self._mode = mode
        self._refresh()

    def _refresh(self):
        # 激活态 — 渐变蓝紫 + 白字 + 内阴影模拟按压
        active = f"""
            color: #ffffff;
            background: {ACTIVE_GRADIENT};
            border: 1px solid transparent;
            padding: 0 22px;
        """
        active_hover = f"""
            color: #ffffff;
            background: {ACTIVE_HOVER};
            border: 1px solid transparent;
            padding: 0 22px;
        """

        # 非激活态 — 浅灰底
        inactive = f"""
            color: {C.TEXT_SEC};
            background: {C.GRAY_200};
            border: 1px solid {C.BORDER};
            padding: 0 22px;
        """
        inactive_hover = f"""
            color: {C.TEXT};
            background: {C.GRAY_300};
            border: 1px solid {C.BORDER_ACCENT};
            padding: 0 22px;
        """

        if self._mode == "multi":
            self._btn_multi.setStyleSheet(f"""
                QPushButton {{ {active} border-radius: {RADIUS_MD}px 0 0 {RADIUS_MD}px; }}
                QPushButton:hover {{ {active_hover} border-radius: {RADIUS_MD}px 0 0 {RADIUS_MD}px; }}
            """)
            self._btn_single.setStyleSheet(f"""
                QPushButton {{ {inactive} border-radius: 0 {RADIUS_MD}px {RADIUS_MD}px 0; }}
                QPushButton:hover {{ {inactive_hover} border-radius: 0 {RADIUS_MD}px {RADIUS_MD}px 0; }}
            """)
        else:
            self._btn_multi.setStyleSheet(f"""
                QPushButton {{ {inactive} border-radius: {RADIUS_MD}px 0 0 {RADIUS_MD}px; }}
                QPushButton:hover {{ {inactive_hover} border-radius: {RADIUS_MD}px 0 0 {RADIUS_MD}px; }}
            """)
            self._btn_single.setStyleSheet(f"""
                QPushButton {{ {active} border-radius: 0 {RADIUS_MD}px {RADIUS_MD}px 0; }}
                QPushButton:hover {{ {active_hover} border-radius: 0 {RADIUS_MD}px {RADIUS_MD}px 0; }}
            """)
