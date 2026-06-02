"""右侧日志面板 — IDE暗色终端风格"""
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QTextEdit, QVBoxLayout, QLabel, QWidget
from ..theme import C, sans, mono, frosted_shadow


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setStyleSheet(f"""
            background: {C.TERM_HEADER};
            border: 1px solid {C.TERM_BORDER};
            border-bottom: none;
            border-radius: 12px 12px 0 0;
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(10)

        title = QLabel("OUTPUT")
        title.setFont(sans(9, bold=True))
        title.setStyleSheet(f"color: {C.TERM_LINE_NUM}; background: transparent;")
        hl.addWidget(title)

        hl.addStretch(1)

        # 状态指示灯
        self.status_dot = QLabel("●")
        self.status_dot.setFont(sans(8))
        self.status_dot.setStyleSheet(f"color: {C.SUCCESS}; background: transparent;")
        hl.addWidget(self.status_dot)

        status_text = QLabel("READY")
        status_text.setFont(sans(8, bold=True))
        status_text.setStyleSheet(f"color: {C.TERM_GREEN}; background: transparent;")
        hl.addWidget(status_text)

        l.addWidget(header)

        # ── Terminal ──
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(mono(9))
        self.terminal.setStyleSheet(f"""
            QTextEdit {{
                background: {C.TERM_BG};
                color: {C.TERM_TEXT};
                border: 1px solid {C.TERM_BORDER};
                border-radius: 0 0 12px 12px;
                padding: 14px;
                line-height: 1.6;
                selection-background-color: {C.ACCENT};
                selection-color: #ffffff;
            }}
            QScrollBar:vertical {{
                background: {C.TERM_BG};
                width: 5px;
                margin: 4px 2px 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C.TERM_BORDER};
                border-radius: 3px;
                min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.TERM_LINE_NUM};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        l.addWidget(self.terminal, stretch=1)

        self.setGraphicsEffect(frosted_shadow(self))

    def log(self, text, color=C.TERM_TEXT):
        self.terminal.moveCursor(QTextCursor.MoveOperation.End)
        c = self.terminal.textColor()
        self.terminal.setTextColor(color)
        self.terminal.insertPlainText(text)
        self.terminal.setTextColor(c)
        sb = self.terminal.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear(self):
        self.terminal.clear()
