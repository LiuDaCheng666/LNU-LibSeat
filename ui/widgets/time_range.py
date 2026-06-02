"""时间段选择器 — 精致时间输入"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget
from ..theme import C, sans, mono, RADIUS_MD


class TimeInput(QLineEdit):
    def __init__(self, default="09:00", parent=None):
        super().__init__(default, parent)
        self.setFont(mono(14, bold=True))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMaxLength(5)
        self.setFixedSize(72, 38)
        self._orig = default
        self.setStyleSheet(f"""
            QLineEdit {{
                background: #ffffff;
                border: 1px solid {C.BORDER};
                border-radius: {RADIUS_MD}px;
                color: {C.ACCENT};
                font-weight: bold;
            }}
            QLineEdit:hover {{
                border: 1px solid {C.BORDER_ACCENT};
                background: #fefeff;
            }}
            QLineEdit:focus {{
                border: 2px solid {C.BORDER_FOCUS};
                background: #ffffff;
            }}
        """)


class TimeRangePicker(QWidget):
    def __init__(self, start="09:00", end="21:00", parent=None):
        super().__init__(parent)
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)

        self.start_input = TimeInput(start)
        l.addWidget(self.start_input)

        # 分隔线 + 箭头
        sep = QLabel("→")
        sep.setFont(sans(12, bold=True))
        sep.setStyleSheet(f"color: {C.ACCENT}; background: transparent;")
        sep.setFixedWidth(24)
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(sep)

        self.end_input = TimeInput(end)
        l.addWidget(self.end_input)

        hint = QLabel("全天目标时段")
        hint.setFont(sans(9))
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        l.addWidget(hint)
        l.addStretch(1)

    def values(self):
        return (self.start_input.text().strip(), self.end_input.text().strip())

    def set_values(self, start, end):
        self.start_input.setText(start)
        self.end_input.setText(end)
