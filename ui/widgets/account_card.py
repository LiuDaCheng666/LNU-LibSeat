"""账号卡片 — 现代风格，最多3个，可动态增删"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)
from ..theme import C, sans, RADIUS_MD, RADIUS_LG


def _input(placeholder, icon="", is_password=False):
    """带图标前缀的输入框"""
    wrapper = QWidget()
    wrapper.setStyleSheet(f"""
        background: {C.INPUT};
        border: 1px solid {C.BORDER};
        border-radius: {RADIUS_MD}px;
    """)
    wl = QHBoxLayout(wrapper)
    wl.setContentsMargins(0, 0, 0, 0)
    wl.setSpacing(0)

    # 图标
    if icon:
        icon_lbl = QLabel(icon)
        icon_lbl.setFont(sans(11))
        icon_lbl.setFixedWidth(32)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            color: {C.TEXT_MUTED};
            background: transparent;
            border: none;
        """)
        wl.addWidget(icon_lbl)

    # 输入框本体
    e = QLineEdit()
    e.setFont(sans(10))
    e.setMinimumHeight(34)
    e.setPlaceholderText(placeholder)
    if is_password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setStyleSheet(f"""
        QLineEdit {{
            background: transparent;
            border: none;
            padding: 0 12px 0 {0 if icon else 12}px;
            color: {C.TEXT};
        }}
        QLineEdit:focus {{ border: none; }}
    """)
    wl.addWidget(e, stretch=1)

    # 存储引用以便样式控制
    wrapper._input = e
    wrapper._orig_style = wrapper.styleSheet()

    # 使用事件过滤器处理 focus/hover
    def on_focus():
        wrapper.setStyleSheet(f"""
            background: {C.INPUT_HOVER};
            border: 1.5px solid {C.BORDER_FOCUS};
            border-radius: {RADIUS_MD}px;
        """)
    def on_blur():
        wrapper.setStyleSheet(wrapper._orig_style)
    def on_enter():
        if not e.hasFocus():
            wrapper.setStyleSheet(f"""
                background: {C.INPUT_HOVER};
                border: 1px solid {C.BORDER_ACCENT};
                border-radius: {RADIUS_MD}px;
            """)
    def on_leave():
        if not e.hasFocus():
            wrapper.setStyleSheet(wrapper._orig_style)

    e.focusInEvent = lambda evt: (QLineEdit.focusInEvent(e, evt), on_focus())
    e.focusOutEvent = lambda evt: (QLineEdit.focusOutEvent(e, evt), on_blur())
    e.enterEvent = lambda evt: (QLineEdit.enterEvent(e, evt), on_enter())
    e.leaveEvent = lambda evt: (QLineEdit.leaveEvent(e, evt), on_leave())

    wrapper._get_text = e.text
    wrapper._set_text = e.setText
    return wrapper


class AccountCard(QWidget):
    removed = Signal(object)

    def __init__(self, index=0, parent=None):
        super().__init__(parent)
        self._index = index
        self.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {C.GRAY_50},
                stop:1 {C.GRAY_200});
            border: 1px solid {C.BORDER_LIGHT};
            border-radius: {RADIUS_LG}px;
        """)
        self.setMinimumHeight(66)

        l = QHBoxLayout(self)
        l.setContentsMargins(12, 10, 12, 10)
        l.setSpacing(10)

        # 圆形序号徽章
        badge = QLabel(f"{index + 1}")
        badge.setFont(sans(10, bold=True))
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            color: #ffffff;
            background: {C.PURPLE};
            border-radius: 14px;
            font-weight: bold;
        """)
        l.addWidget(badge)

        # 学号输入
        self.acc_wrapper = _input("学号 / 工号", icon="👤")
        l.addWidget(self.acc_wrapper, stretch=3)

        # 密码输入
        self.pwd_wrapper = _input("密码", icon="🔒", is_password=True)
        l.addWidget(self.pwd_wrapper, stretch=2)

        # 删除按钮（仅非首个卡片显示）
        if index > 0:
            rm_btn = QPushButton("✕")
            rm_btn.setFont(sans(11))
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.setFixedSize(28, 28)
            rm_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {C.TEXT_DIM};
                    background: transparent;
                    border: none;
                    border-radius: 14px;
                }}
                QPushButton:hover {{
                    color: #ffffff;
                    background: {C.ERR};
                }}
            """)
            rm_btn.clicked.connect(lambda: self.removed.emit(self))
            l.addWidget(rm_btn)

    def values(self):
        return (self.acc_wrapper._get_text().strip(),
                self.pwd_wrapper._get_text().strip())

    def set_values(self, acc, pwd):
        self.acc_wrapper._set_text(acc)
        self.pwd_wrapper._set_text(pwd)


class AccountPanel(QWidget):
    MAX_CARDS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._mode = "multi"
        self._hidden_cards = []  # 单账号模式下隐藏的卡片引用
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(2, 4, 2, 0)
        self._outer.setSpacing(8)
        self._add_btn_row()
        self._add_card(0)

    def _add_card(self, index):
        if len(self._cards) >= self.MAX_CARDS:
            return
        card = AccountCard(index)
        card.removed.connect(self._remove_card)
        self._cards.append(card)
        self._outer.insertWidget(self._outer.count() - 1, card)
        self._update_add_btn()

    def _remove_card(self, card):
        if len(self._cards) <= 1:
            return
        # 同步清理隐藏记录
        if card in self._hidden_cards:
            self._hidden_cards.remove(card)
        self._cards.remove(card)
        card.deleteLater()
        self._reindex()
        self._update_add_btn()

    def _reindex(self):
        for i, card in enumerate(self._cards):
            card._index = i
            card.removed.disconnect()
            card.removed.connect(self._remove_card)

    def _update_add_btn(self):
        visible_count = sum(1 for c in self._cards if not c.isHidden())
        self._add_btn.setVisible(
            len(self._cards) < self.MAX_CARDS and self._mode == "multi"
        )

    def _add_btn_row(self):
        row = QHBoxLayout()
        self._add_btn = QPushButton("+  添 加 账 号")
        self._add_btn.setFont(sans(10))
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.ACCENT};
                background: {C.GRAY_50};
                border: 1.5px dashed {C.BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: {C.ACCENT};
                background: {C.ACCENT_SOFT};
                color: {C.ACCENT_HOT};
            }}
        """)
        self._add_btn.clicked.connect(lambda: self._add_card(len(self._cards)))
        row.addWidget(self._add_btn)
        row.addStretch(1)
        self._outer.addLayout(row)

    def set_mode(self, mode):
        """单账号模式只显示第1个卡片；多账号模式恢复全部"""
        self._mode = mode
        if mode == "single":
            self._hidden_cards.clear()
            # 隐藏第2个及之后的卡片
            for i, card in enumerate(self._cards):
                if i > 0:
                    card.setVisible(False)
                    if card not in self._hidden_cards:
                        self._hidden_cards.append(card)
            # 隐藏添加按钮
            self._add_btn.setVisible(False)
        else:
            # 恢复所有卡片
            for card in self._hidden_cards:
                card.setVisible(True)
            self._hidden_cards.clear()
            self._update_add_btn()

    def accounts(self, include_hidden=True):
        """收集账号数据。include_hidden=False 时只收集可见卡片（用于执行分配）。"""
        result = []
        for card in self._cards:
            if not include_hidden and self._mode == "single" and card.isHidden():
                continue
            acc, pwd = card.values()
            if acc:
                result.append((acc, pwd))
        return result

    def set_accounts(self, accounts):
        while len(self._cards) < min(len(accounts), self.MAX_CARDS):
            self._add_card(len(self._cards))
        while len(self._cards) > max(len(accounts), 1):
            if len(self._cards) > 1:
                self._remove_card(self._cards[-1])
        for i, (acc, pwd) in enumerate(accounts):
            if i < len(self._cards):
                self._cards[i].set_values(acc, pwd)
        self.set_mode(self._mode)
        self._update_add_btn()
