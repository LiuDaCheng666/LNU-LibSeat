"""操作按钮 — 渐变 + 阴影效果"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget
from ..theme import C, sans, soft_glow, elevated_shadow


GRADIENT_ACTIVE = f"""
    qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C.GRADIENT_PURPLE_START},
        stop:1 {C.GRADIENT_BLUE_END})
"""

GRADIENT_ACTIVE_HOT = f"""
    qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C.PURPLE_HOT},
        stop:1 {C.ACCENT_HOT})
"""


class ActionButton(QPushButton):
    def __init__(self, text, accent=True, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(sans(11, bold=True))
        self.setMinimumHeight(46)
        self._accent = accent
        self._apply_style(False)

    def _apply_style(self, hover):
        if self._accent:
            bg = GRADIENT_ACTIVE_HOT if hover else GRADIENT_ACTIVE
            self.setStyleSheet(f"""
                QPushButton {{
                    color: #ffffff;
                    background: {bg};
                    border: none;
                    border-radius: 10px;
                    padding: 0 32px;
                    font-weight: bold;
                }}
                QPushButton:disabled {{
                    background: {C.GRAY_400};
                    color: {C.TEXT_DIM};
                }}
            """)
        else:
            if hover:
                self.setStyleSheet(f"""
                    QPushButton {{
                        color: {C.ERR};
                        background: {C.ERR_SOFT};
                        border: 1.5px solid {C.ERR};
                        border-radius: 10px;
                        padding: 0 24px;
                    }}
                """)
            else:
                self.setStyleSheet(f"""
                    QPushButton {{
                        color: {C.TEXT_MUTED};
                        background: {C.GRAY_100};
                        border: 1px solid {C.BORDER};
                        border-radius: 10px;
                        padding: 0 24px;
                    }}
                    QPushButton:disabled {{
                        background: {C.GRAY_300};
                        color: {C.TEXT_DIM};
                    }}
                """)

    def enterEvent(self, e):
        self._apply_style(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._apply_style(False)
        super().leaveEvent(e)


class ActionBar(QWidget):
    start_clicked = Signal()
    stop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 6, 0, 0)
        l.setSpacing(14)

        self.btn_start = ActionButton("▶  开 始 分 配")
        self.btn_start.clicked.connect(self.start_clicked.emit)
        self.btn_start.setGraphicsEffect(elevated_shadow(self.btn_start))
        l.addWidget(self.btn_start)

        self.btn_stop = ActionButton("■  停  止", accent=False)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setGraphicsEffect(soft_glow(self.btn_stop, C.ERR, blur=8, alpha=0))
        self.btn_stop.clicked.connect(self.stop_clicked.emit)
        l.addWidget(self.btn_stop)
        l.addStretch(1)

    def set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)

        if running:
            # 停止按钮启用时 — 红色柔光
            self.btn_stop.setGraphicsEffect(
                soft_glow(self.btn_stop, C.ERR, blur=14, alpha=30)
            )
        else:
            # 停止按钮禁用时 — 无光
            self.btn_stop.setGraphicsEffect(
                soft_glow(self.btn_stop, C.ERR, blur=8, alpha=0)
            )
