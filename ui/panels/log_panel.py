"""右侧日志面板 — IDE暗色终端风格"""
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QTextEdit, QVBoxLayout, QLabel, QWidget
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

        # ── Single-account plan status ──
        self.plan_box = QFrame()
        self.plan_box.setObjectName("planBox")
        self.plan_box.setStyleSheet(f"""
            QFrame#planBox {{
                background: {C.TERM_BG};
                border-left: 1px solid {C.TERM_BORDER};
                border-right: 1px solid {C.TERM_BORDER};
                border-top: 1px solid {C.TERM_BORDER};
                border-bottom: none;
            }}
        """)
        pl = QVBoxLayout(self.plan_box)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(6)

        self.plan_title = QLabel("续约计划")
        self.plan_title.setFont(sans(9, bold=True))
        self.plan_title.setStyleSheet(f"color: {C.SUCCESS}; background: transparent;")
        pl.addWidget(self.plan_title)

        self.plan_body = QLabel("")
        self.plan_body.setWordWrap(True)
        self.plan_body.setFont(mono(8))
        self.plan_body.setStyleSheet(f"color: {C.TERM_TEXT}; background: transparent; line-height: 1.45;")
        pl.addWidget(self.plan_body)
        self.plan_box.setVisible(False)
        l.addWidget(self.plan_box)

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

    def set_plan_status(self, payload: dict):
        if not payload or not payload.get("active"):
            self.plan_box.setVisible(False)
            self.plan_body.setText("")
            return

        current = payload.get("current_booking") or {}
        pending = payload.get("pending_next_slot") or {}
        upcoming = payload.get("upcoming_slots") or []
        target_range = payload.get("target_range") or ""
        notify_at = payload.get("notify_at") or ""
        countdown = payload.get("countdown") or "等待计算"
        phase = payload.get("phase") or "waiting_next_scan"

        phase_text = {
            "dry_run_preview": "测试预览，未启动自动换座",
            "waiting_next_scan": "已启用，等待下一次扫描",
            "pending_change_confirmation": "已找到下一段，等待确认",
            "changing": "正在换座",
            "current_cancelled_booking_next": "已取消当前预约，正在预约下一段",
            "no_next_seat": "未找到下一段",
        }.get(phase, phase)

        lines = [f"状态: {phase_text}"]
        if target_range:
            lines.append(f"目标覆盖: {target_range}")
        if current:
            lines.append(
                "当前预约: "
                f"{current.get('room_name') or '未知房间'} / 座位{current.get('seat_num') or '?'} / "
                f"{current.get('start_time') or '?'}-{current.get('end_time') or '?'}"
            )
        if notify_at:
            prefix = "预计下一次扫描" if payload.get("dry_run") else "下一次扫描"
            lines.append(f"{prefix}: {notify_at} / 倒计时: {countdown}")
        if pending:
            lines.append(
                "待确认下一段: "
                f"{pending.get('room_name') or '未知房间'} / 座位{pending.get('seat_num') or '?'} / "
                f"{pending.get('start') or '?'}-{pending.get('end') or '?'}"
            )
        if upcoming:
            lines.append("后续预案: 待扫描复验，未预约")
            for idx, slot in enumerate(upcoming[:3], start=1):
                lines.append(
                    f"  第{idx}段预案: {slot.get('room_name') or '未知房间'} / "
                    f"座位{slot.get('seat_num') or '?'} / "
                    f"{slot.get('start') or '?'}-{slot.get('end') or '?'}"
                )

        self.plan_body.setText("\n".join(lines))
        self.plan_box.setVisible(True)
