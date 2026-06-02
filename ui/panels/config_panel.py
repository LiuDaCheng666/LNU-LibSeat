"""左侧配置面板 — 现代磨砂卡片 + 主题支持"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QVBoxLayout, QWidget, QScrollArea, QPushButton,
)
from ..theme import (
    C, sans, mono, frosted_shadow, card_shadow,
    combo_style, combo_popup,
    scrollbar_style, scrollbar_handle, scrollbar_hover,
    RADIUS_XL, RADIUS_MD, RADIUS_LG,
    on_theme_changed,
)
from ..config_store import save_config, load_config
from ..widgets.account_card import AccountPanel
from ..widgets.animated_frame import AnimatedGradientFrame
from ..widgets.time_range import TimeRangePicker
from ..widgets.toggle_group import ToggleGroup
from ..widgets.action_button import ActionBar

ROOM_DATA = {
    "崇山校区图书馆": [
        "二楼书库北", "二楼书库南", "二楼背诵长廊",
        "三楼智慧研修空间", "三楼理科书库",
        "四楼北自习室", "四楼南自习室", "四楼自习室406",
    ],
    "蒲河校区图书馆": [
        "三楼走廊", "4楼阅览室", "四楼走廊", "5楼阅览室", "五楼走廊",
        "6楼阅览室", "六楼走廊", "704", "706", "707", "708",
        "七楼走廊", "智慧空间",
    ],
}

CROSS_ROOM_NOTES = {
    "崇山校区图书馆": {
        "四楼自习室406": "仅限研究生预约",
    },
}

# 非纯数字座位号格式的房间（如 A-08-1），不显示优先座位配置
NON_INTEGER_SEAT_ROOMS = {"二楼背诵长廊"}

MAX_PREFERRED_SEATS = 10


# ═══════════════════════════════════
#  无滚轮 ComboBox（仅点击选择）
# ═══════════════════════════════════

class NoScrollComboBox(QComboBox):
    """禁用鼠标滚轮的 QComboBox — 只允许鼠标点击展开后选择"""

    def wheelEvent(self, event):
        event.ignore()


# ═══════════════════════════════════
#  可折叠高级设置面板
# ═══════════════════════════════════

class CollapsibleSection(QWidget):
    """可点击标题栏折叠/展开内容区域"""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._expanded = False

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # 标题栏
        self._header = QPushButton()
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setFlat(True)
        self._header.clicked.connect(self._toggle)
        self._outer.addWidget(self._header)

        # 内容容器
        self._content = QWidget()
        self._content.setVisible(False)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 8, 12, 12)
        self._content_layout.setSpacing(8)
        self._outer.addWidget(self._content)

        self._title_text = title
        self._refresh_header()

    def _refresh_header(self):
        arrow = "▾" if self._expanded else "▸"
        self._header.setText(f"  {arrow}  {self._title_text}")
        self._header.setFont(sans(9, bold=True))
        self._header.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_MUTED};
                background: transparent;
                border: 1px solid {C.BORDER_LIGHT};
                border-radius: {RADIUS_MD}px;
                padding: 8px 10px;
                text-align: left;
            }}
            QPushButton:hover {{
                color: {C.ACCENT};
                border-color: {C.BORDER_ACCENT};
                background: {C.ACCENT_SOFT};
            }}
        """)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._refresh_header()

    def addWidget(self, widget):
        self._content_layout.addWidget(widget)

    def addLayout(self, layout):
        self._content_layout.addLayout(layout)

    def set_content_style(self, style: str):
        self._content.setStyleSheet(style)

    def refresh_theme(self):
        self._refresh_header()
        # 递归刷新内容中的已知控件
        _refresh_children(self._content)


def _refresh_children(widget):
    """递归刷新控件的主题相关样式（简单实现：触发布局更新）"""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    for child in widget.findChildren(QWidget):
        child.style().unpolish(child)
        child.style().polish(child)


# ═══════════════════════════════════
#  卡片容器
# ═══════════════════════════════════

def _card():
    """磨砂卡片容器"""
    f = QFrame()
    f.setObjectName("configCard")
    f.setStyleSheet(_card_sheet())
    f.setGraphicsEffect(frosted_shadow(f))
    l = QVBoxLayout(f)
    l.setContentsMargins(18, 16, 18, 16)
    l.setSpacing(10)
    return f, l


def _card_sheet():
    return f"""
        #{'configCard'} {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {C.GRAY_50},
                stop:1 {C.GRAY_100});
            border: 1px solid {C.BORDER_LIGHT};
            border-radius: {RADIUS_XL}px;
        }}
    """


# ═══════════════════════════════════
#  UI 工具函数
# ═══════════════════════════════════

def _section(title, accent_color=None):
    """带彩色左侧竖线指示的标题"""
    if accent_color is None:
        accent_color = C.ACCENT
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)

    bar = QLabel("")
    bar.setFixedSize(3, 14)
    bar.setStyleSheet(f"""
        background: {accent_color};
        border-radius: 2px;
    """)
    row.addWidget(bar)

    lbl = QLabel(title.upper())
    lbl.setFont(sans(8, bold=True))
    lbl.setStyleSheet(f"""
        color: {C.TEXT_DIM}; background: transparent;
        letter-spacing: 2px;
    """)
    row.addWidget(lbl)
    row.addStretch(1)
    return row


def _combo(values):
    """创建禁用滚轮的下拉框"""
    cb = NoScrollComboBox()
    cb.setFont(sans(10))
    cb.setMinimumHeight(36)
    cb.addItems(values)
    cb.setCursor(Qt.CursorShape.PointingHandCursor)
    cb.setStyleSheet(f"""
        QComboBox {{
            {combo_style()}
        }}
        QComboBox:focus {{
            border: 1.5px solid {C.BORDER_FOCUS};
            background: {C.INPUT_HOVER};
        }}
        QComboBox:hover {{
            border: 1px solid {C.BORDER_ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 28px;
            subcontrol-position: center right;
            subcontrol-origin: padding;
            padding-right: 8px;
        }}
        QComboBox::down-arrow {{
            width: 10px;
            height: 10px;
        }}
        QComboBox QAbstractItemView {{
            {combo_popup()}
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 6px 12px;
            border-radius: {RADIUS_MD}px;
            min-height: 28px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background: {C.ACCENT_SOFT};
            color: {C.TEXT};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background: {C.ACCENT};
            color: #ffffff;
        }}
    """)
    return cb


def _check(text, default=True):
    cb = QCheckBox(text)
    cb.setFont(sans(10))
    cb.setCursor(Qt.CursorShape.PointingHandCursor)
    cb.setChecked(default)
    cb.setStyleSheet(f"""
        QCheckBox {{
            color: {C.TEXT_SEC};
            background: transparent;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 5px;
            border: 1.5px solid {C.BORDER};
            background: {C.INPUT};
        }}
        QCheckBox::indicator:hover {{
            border-color: {C.ACCENT};
            background: {C.ACCENT_SOFT};
        }}
        QCheckBox::indicator:checked {{
            background: {C.ACCENT};
            border-color: {C.ACCENT};
        }}
        QCheckBox::indicator:checked:hover {{
            background: {C.ACCENT_HOT};
            border-color: {C.ACCENT_HOT};
        }}
    """)
    return cb


def _room_select_check(text, default=False):
    cb = QCheckBox(text)
    cb.setFont(sans(9))
    cb.setCursor(Qt.CursorShape.PointingHandCursor)
    cb.setChecked(default)
    cb.setMinimumHeight(28)
    cb.setStyleSheet(f"""
        QCheckBox {{
            color: {C.TEXT_SEC};
            background: {C.INPUT};
            border: 1px solid {C.BORDER_LIGHT};
            border-radius: {RADIUS_MD}px;
            padding: 4px 8px;
            spacing: 8px;
        }}
        QCheckBox:hover {{
            border-color: {C.ACCENT};
            background: {C.ACCENT_SOFT};
        }}
        QCheckBox:checked {{
            color: {C.TEXT};
            border-color: {C.SUCCESS};
            background: {C.SUCCESS_SOFT};
            font-weight: 600;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 5px;
            border: 1.5px solid {C.BORDER};
            background: {C.INPUT};
        }}
        QCheckBox::indicator:hover {{
            border-color: {C.ACCENT};
        }}
        QCheckBox::indicator:checked {{
            background: {C.SUCCESS};
            border-color: {C.SUCCESS};
        }}
    """)
    return cb


# ═══════════════════════════════════
#  ConfigPanel
# ═══════════════════════════════════

class ConfigPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setMinimumWidth(350)
        self._saved_preferred_seats = {}
        self._saved_cross_room_rooms = {}
        self._cross_room_current_campus = ""
        self.cross_room_checks = []
        self._widgets_for_theme = []  # 跟踪需要在主题切换时刷新的控件

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ {scrollbar_style()} }}
            QScrollBar::handle:vertical {{ {scrollbar_handle()} }}
            QScrollBar::handle:vertical:hover {{ {scrollbar_hover()} }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(14)

        # ══════ 账号 ══════
        acard, acl = _card()
        acl.addLayout(_section("账  号", C.PURPLE))
        acl.addSpacing(2)
        hint = QLabel("最多添加 3 个账号（学号/工号 + 密码）")
        hint.setFont(sans(8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        acl.addWidget(hint)
        self.accounts = AccountPanel()
        acl.addWidget(self.accounts)
        bl.addWidget(acard)

        # ══════ 目标设置 ══════
        gcard, gcl = _card()
        gcl.addLayout(_section("目  标  设  置"))

        # 校区
        cr = QHBoxLayout()
        cr.setSpacing(10)
        cl = QLabel("校  区")
        cl.setFont(sans(10))
        cl.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        cl.setFixedWidth(52)
        cr.addWidget(cl)
        self.cb_campus = _combo(list(ROOM_DATA.keys()))
        self.cb_campus.currentTextChanged.connect(self._on_campus_changed)
        cr.addWidget(self.cb_campus, stretch=1)
        gcl.addLayout(cr)

        # 房间
        rr = QHBoxLayout()
        rr.setSpacing(10)
        rl = QLabel("房  间")
        rl.setFont(sans(10))
        rl.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        rl.setFixedWidth(52)
        rr.addWidget(rl)
        self.cb_room = _combo(ROOM_DATA["崇山校区图书馆"])
        self.cb_room.currentTextChanged.connect(self._on_room_changed)
        rr.addWidget(self.cb_room, stretch=1)
        gcl.addLayout(rr)

        # 时段
        tr = QHBoxLayout()
        tr.setSpacing(10)
        tl = QLabel("时  段")
        tl.setFont(sans(10))
        tl.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        tl.setFixedWidth(52)
        tr.addWidget(tl)
        self.time_range = TimeRangePicker()
        tr.addWidget(self.time_range, stretch=1)
        gcl.addLayout(tr)

        gcl.addSpacing(4)

        # 分割线
        sep = QLabel("")
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C.BORDER_LIGHT};")
        gcl.addWidget(sep)

        self.cross_room = _check("允许跨房间 / 跨楼层搜索（优先同房间）")
        self.cross_room.stateChanged.connect(lambda _: self._update_cross_room_visibility())
        gcl.addWidget(self.cross_room)

        # ── 跨房间范围容器（动态渐变框：微呼吸动画 + 圆角 + 阴影）──
        self._cross_rooms_container = AnimatedGradientFrame(accent_side="left")
        self._cross_rooms_container.setGraphicsEffect(card_shadow(self._cross_rooms_container))
        crc_l = QVBoxLayout(self._cross_rooms_container)
        crc_l.setContentsMargins(12, 10, 12, 10)
        crc_l.setSpacing(8)

        cross_header = QHBoxLayout()
        cross_header.setContentsMargins(0, 0, 0, 0)
        cross_header.setSpacing(8)
        ch_bar = QLabel("")
        ch_bar.setFixedSize(3, 14)
        ch_bar.setStyleSheet(f"background: {C.ACCENT}; border-radius: 2px;")
        cross_header.addWidget(ch_bar)
        ch_lbl = QLabel("跨 房 间 范 围")
        ch_lbl.setFont(sans(8, bold=True))
        ch_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 2px;")
        cross_header.addWidget(ch_lbl)
        cross_header.addStretch(1)
        crc_l.addLayout(cross_header)

        cross_note = QLabel("目标房间始终扫描；跨房间只扫描下方勾选的房间。")
        cross_note.setFont(sans(8))
        cross_note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        cross_note.setWordWrap(True)
        crc_l.addWidget(cross_note)

        self._cross_rooms_grid = QGridLayout()
        self._cross_rooms_grid.setContentsMargins(0, 0, 0, 0)
        self._cross_rooms_grid.setHorizontalSpacing(6)
        self._cross_rooms_grid.setVerticalSpacing(6)
        crc_l.addLayout(self._cross_rooms_grid)
        gcl.addWidget(self._cross_rooms_container)

        # ── 邮箱 ──
        email_row = QHBoxLayout()
        email_row.setSpacing(10)
        email_lbl = QLabel("邮  箱")
        email_lbl.setFont(sans(10))
        email_lbl.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        email_lbl.setFixedWidth(52)
        email_row.addWidget(email_lbl)
        self.receiver_email = QLineEdit()
        self.receiver_email.setFont(sans(10))
        self.receiver_email.setPlaceholderText("留空则不发送邮件")
        self.receiver_email.setMinimumHeight(34)
        self.receiver_email.setStyleSheet(f"""
            QLineEdit {{
                background: {C.INPUT};
                border: 1px solid {C.BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 0 10px;
                color: {C.TEXT};
            }}
            QLineEdit:focus {{ border: 1.5px solid {C.BORDER_FOCUS}; }}
            QLineEdit:hover {{ border: 1px solid {C.BORDER_ACCENT}; }}
        """)
        email_row.addWidget(self.receiver_email, stretch=1)
        gcl.addLayout(email_row)

        # ══════ 优先座位（容器） ══════
        self._prefer_container = QFrame()
        self._prefer_container.setStyleSheet("background: transparent; border: none;")
        pfc = QVBoxLayout(self._prefer_container)
        pfc.setContentsMargins(0, 0, 0, 0)
        pfc.setSpacing(4)

        gcl.addSpacing(4)
        sep2 = QLabel("")
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {C.BORDER_LIGHT};")
        pfc.addWidget(sep2)

        # 标题
        prefer_header = QHBoxLayout()
        prefer_header.setContentsMargins(0, 2, 0, 0)
        prefer_header.setSpacing(8)
        bar2 = QLabel("")
        bar2.setFixedSize(3, 14)
        bar2.setStyleSheet(f"background: {C.WARN}; border-radius: 2px;")
        prefer_header.addWidget(bar2)
        plbl = QLabel("优 先 座 位")
        plbl.setFont(sans(8, bold=True))
        plbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 2px;")
        prefer_header.addWidget(plbl)
        prefer_header.addStretch(1)
        hint_p = QLabel("（最多10个，000=无优先）")
        hint_p.setFont(sans(8))
        hint_p.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        prefer_header.addWidget(hint_p)
        pfc.addLayout(prefer_header)

        # 座位输入网格 2行×5列
        self.prefer_inputs = []
        for row_idx in range(2):
            pr = QHBoxLayout()
            pr.setSpacing(6)
            for col_idx in range(5):
                i = row_idx * 5 + col_idx
                inp = QLineEdit()
                inp.setFont(mono(11, bold=True))
                inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
                inp.setMaxLength(3)
                inp.setPlaceholderText("000")
                inp.setFixedSize(58, 30)
                inp.setStyleSheet(f"""
                    QLineEdit {{
                        background: {C.INPUT};
                        border: 1px solid {C.BORDER};
                        border-radius: {RADIUS_MD}px;
                        color: {C.TEXT};
                    }}
                    QLineEdit:focus {{ border: 1.5px solid {C.ACCENT}; }}
                    QLineEdit:hover {{ border: 1px solid {C.BORDER_ACCENT}; }}
                """)
                inp._prefer_index = i
                self.prefer_inputs.append(inp)
                pr.addWidget(inp)
            pfc.addLayout(pr)

        # 提示
        prefer_note = QLabel("输入要优先选择的座位号（3位数字如 001、054、169）。留空或填000表示无优先，由算法自动选择。")
        prefer_note.setFont(sans(8))
        prefer_note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        prefer_note.setWordWrap(True)
        pfc.addWidget(prefer_note)

        gcl.addWidget(self._prefer_container)

        # ══════ 优先模式 — 选座策略（修复：标签自适应宽度） ══════
        pm_row = QHBoxLayout()
        pm_row.setSpacing(10)
        pml = QLabel("选座策略")
        pml.setFont(sans(10))
        pml.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        pml.setFixedWidth(64)  # 修复：加宽以免"略"字被遮挡
        pm_row.addWidget(pml)
        self.priority_mode_toggle = ToggleGroup()
        self.priority_mode_toggle._btn_multi.setText("⌂  最长时段优先")
        self.priority_mode_toggle._btn_single.setText("★  优先座位优先")
        self.priority_mode_toggle._select("multi")
        pm_row.addWidget(self.priority_mode_toggle, stretch=1)
        gcl.addLayout(pm_row)

        # 单账号设置（默认隐藏，动态渐变框：微呼吸动画 + 圆角 + 阴影）
        self.single_frame = AnimatedGradientFrame(accent_side="left")
        self.single_frame.setGraphicsEffect(card_shadow(self.single_frame))
        sf_l = QVBoxLayout(self.single_frame)
        sf_l.setContentsMargins(16, 14, 16, 14)
        sf_l.setSpacing(10)

        noti_row = QHBoxLayout()
        noti_row.setSpacing(6)
        nl = QLabel("提前")
        nl.setFont(sans(10))
        nl.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        noti_row.addWidget(nl)
        self.notify_min = NoScrollComboBox()
        self.notify_min.setFont(sans(10))
        self.notify_min.setMinimumHeight(32)
        self.notify_min.addItems(["15", "20", "25", "30", "40", "50", "60"])
        self.notify_min.setCurrentIndex(3)
        self.notify_min.setStyleSheet(f"""
            QComboBox {{
                background: {C.INPUT};
                border: 1px solid {C.BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 0 10px;
                color: {C.ACCENT};
                font-weight: bold;
                min-width: 50px;
            }}
            QComboBox:focus {{ border: 1.5px solid {C.ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                {combo_popup()}
            }}
        """)
        noti_row.addWidget(self.notify_min)
        nl2 = QLabel("分钟前开始查找下一座位")
        nl2.setFont(sans(10))
        nl2.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        noti_row.addWidget(nl2)
        noti_row.addStretch(1)
        sf_l.addLayout(noti_row)

        self.auto_cancel = _check("自动取消并换座（无需弹窗确认，全自动运行）", default=False)
        sf_l.addWidget(self.auto_cancel)
        self.single_frame.setVisible(False)
        gcl.addWidget(self.single_frame)

        # ══════ 高级设置（可折叠，默认收起） ══════
        self.advanced_section = CollapsibleSection("高 级 设 置")
        self.advanced_section.set_content_style(f"""
            background: {C.NESTED_BG};
            border: 1px solid {C.BORDER_LIGHT};
            border-top: none;
            border-radius: 0 0 {RADIUS_MD}px {RADIUS_MD}px;
        """)
        self.dry_run = _check("仅测试 API 抓取并生成方案（不预约）", default=False)
        self.advanced_section.addWidget(self.dry_run)
        gcl.addWidget(self.advanced_section)

        bl.addWidget(gcard)

        # ══════ 模式选择 ══════
        mcard, mcl = _card()
        mcl.addLayout(_section("模  式  选  择"))
        self.toggle = ToggleGroup()
        self.toggle.mode_changed.connect(self._on_mode_changed)
        mcl.addWidget(self.toggle)
        bl.addWidget(mcard)

        # ══════ 操作按钮 ══════
        self.action_bar = ActionBar()
        bl.addWidget(self.action_bar)

        bl.addStretch(1)

        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self._rebuild_cross_room_options()

        # ── 注册主题变更回调 ──
        on_theme_changed(self._on_theme_changed)

    # ──────── 主题刷新 ────────
    def _on_theme_changed(self, theme_name):
        """主题切换时重新刷新所有控件样式"""
        self.setStyleSheet("background: transparent;")
        # 遍历所有子控件触发样式重算
        self.style().unpolish(self)
        self.style().polish(self)
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
        # 刷新可折叠区域
        self.advanced_section.refresh_theme()
        # 强制重绘
        self.update()

    # ──────── 校区/房间联动 ────────
    def _on_campus_changed(self, campus):
        rooms = ROOM_DATA.get(campus, [])
        self.cb_room.clear()
        self.cb_room.addItems(rooms)
        self._update_prefer_visibility()
        self._rebuild_cross_room_options()

    def _on_room_changed(self, room):
        self._update_prefer_visibility()
        self._load_preferred_seats()
        self._rebuild_cross_room_options()

    def _on_mode_changed(self, mode):
        self.single_frame.setVisible(mode == "single")
        # 单账号模式：只显示一个账号位；多账号模式：恢复全部
        self.accounts.set_mode(mode)

    def _cross_room_note(self, campus, room):
        return CROSS_ROOM_NOTES.get(campus, {}).get(room, "")

    def _default_cross_rooms(self, campus, target_room):
        return [
            r for r in ROOM_DATA.get(campus, [])
            if r != target_room and not self._cross_room_note(campus, r)
        ]

    def _persist_cross_room_selection(self):
        if not getattr(self, "cross_room_checks", None):
            return
        campus = self._cross_room_current_campus
        if not campus:
            return
        selected = [
            cb._room_name for cb in self.cross_room_checks
            if cb.isChecked() and getattr(cb, "_room_name", "")
        ]
        saved = dict(self._saved_cross_room_rooms or {})
        saved[campus] = selected
        self._saved_cross_room_rooms = saved

    def _selected_cross_rooms_for_campus(self, campus, target_room):
        saved = self._saved_cross_room_rooms or {}
        if campus in saved:
            return set(saved.get(campus, []))
        return set(self._default_cross_rooms(campus, target_room))

    def _update_cross_room_visibility(self):
        if hasattr(self, "_cross_rooms_container"):
            self._cross_rooms_container.setVisible(self.cross_room.isChecked())

    def _rebuild_cross_room_options(self):
        if not hasattr(self, "_cross_rooms_grid"):
            return

        while self._cross_rooms_grid.count():
            item = self._cross_rooms_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.cross_room_checks = []
        campus = self.cb_campus.currentText()
        target_room = self.cb_room.currentText()
        selected = self._selected_cross_rooms_for_campus(campus, target_room)

        rooms = [r for r in ROOM_DATA.get(campus, []) if r != target_room]
        for idx, room in enumerate(rooms):
            note = self._cross_room_note(campus, room)
            text = f"{room}（{note}）" if note else room
            cb = _room_select_check(text, default=room in selected)
            cb._room_name = room
            cb._label_text = text
            def _refresh_label(checked, box=cb):
                box.setText(("✓  " if checked else "") + box._label_text)
            cb.toggled.connect(_refresh_label)
            _refresh_label(cb.isChecked())
            if note:
                cb.setToolTip(note)
            self.cross_room_checks.append(cb)
            self._cross_rooms_grid.addWidget(cb, idx // 2, idx % 2)

        self._cross_room_current_campus = campus
        self._update_cross_room_visibility()

    def _collect_cross_room_rooms(self):
        self._persist_cross_room_selection()
        campus = self.cb_campus.currentText()
        selected = [
            cb._room_name for cb in self.cross_room_checks
            if cb.isChecked() and getattr(cb, "_room_name", "")
        ]
        all_rooms = dict(self._saved_cross_room_rooms or {})
        all_rooms[campus] = selected
        return all_rooms

    # ──────── 优先座位逻辑 ────────
    def _get_prefer_key(self):
        campus = self.cb_campus.currentText()
        room = self.cb_room.currentText()
        return f"{campus}/{room}" if campus and room else ""

    def _update_prefer_visibility(self):
        room = self.cb_room.currentText()
        hide = room in NON_INTEGER_SEAT_ROOMS
        self._prefer_container.setVisible(not hide)
        self.priority_mode_toggle.setVisible(not hide)

    def _load_preferred_seats(self):
        key = self._get_prefer_key()
        if not key:
            return
        all_prefs = self._saved_preferred_seats or {}
        seats = all_prefs.get(key, [])
        for i, inp in enumerate(self.prefer_inputs):
            if i < len(seats):
                inp.setText(str(seats[i]))
            else:
                inp.setText("")

    def _collect_preferred_seats(self):
        seats = []
        for inp in self.prefer_inputs:
            val = inp.text().strip()
            if val and val != "000" and val != "":
                if val.isdigit():
                    seats.append(f"{int(val):03d}")
                else:
                    seats.append(val)
        return seats

    # ──────── 配置持久化 ────────
    def apply_config(self, cfg: dict):
        """从字典恢复面板状态"""
        self._saved_cross_room_rooms = cfg.get("cross_room_rooms", {})

        # 账号
        accounts = cfg.get("accounts", [])
        if accounts:
            self.accounts.set_accounts(accounts)

        # 校区
        campus = cfg.get("campus", "")
        if campus:
            idx = self.cb_campus.findText(campus)
            if idx >= 0:
                self.cb_campus.setCurrentIndex(idx)

        # 房间
        room = cfg.get("room", "")
        if room:
            idx = self.cb_room.findText(room)
            if idx >= 0:
                self.cb_room.setCurrentIndex(idx)

        # 时段
        self.time_range.set_values(
            cfg.get("day_start", "09:00"),
            cfg.get("day_end", "21:00"),
        )

        # 跨房间
        self.cross_room.setChecked(cfg.get("cross_room", True))
        self.dry_run.setChecked(cfg.get("dry_run", False))
        self.receiver_email.setText(cfg.get("receiver_email", ""))
        self._rebuild_cross_room_options()

        # 模式
        mode = cfg.get("mode", "multi")
        self.toggle.set_mode(mode)
        self.single_frame.setVisible(mode == "single")

        # 提前通知
        pre = str(cfg.get("pre_notify", 30))
        idx = self.notify_min.findText(pre)
        if idx >= 0:
            self.notify_min.setCurrentIndex(idx)

        # 自动取消
        self.auto_cancel.setChecked(cfg.get("auto_cancel", False))

        # 优先座位
        self._saved_preferred_seats = cfg.get("preferred_seats", {})
        self._load_preferred_seats()

        # 优先模式
        p_mode = cfg.get("priority_mode", "longest_first")
        if p_mode == "prefer_first":
            self.priority_mode_toggle._select("single")
        else:
            self.priority_mode_toggle._select("multi")

    def collect(self):
        accounts = self.accounts.accounts()
        start, end = self.time_range.values()
        # 收集优先座位
        key = self._get_prefer_key()
        all_prefs = dict(self._saved_preferred_seats or {})
        current_prefs = self._collect_preferred_seats()
        if current_prefs:
            all_prefs[key] = current_prefs
        elif key in all_prefs:
            del all_prefs[key]
        # 优先模式
        p_mode = "prefer_first" if self.priority_mode_toggle.mode() == "single" else "longest_first"
        return {
            "accounts": accounts,
            "campus": self.cb_campus.currentText(),
            "room": self.cb_room.currentText(),
            "day_start": start,
            "day_end": end,
            "cross_room": self.cross_room.isChecked(),
            "cross_room_rooms": self._collect_cross_room_rooms(),
            "dry_run": self.dry_run.isChecked(),
            "receiver_email": self.receiver_email.text().strip(),
            "mode": self.toggle.mode(),
            "pre_notify": int(self.notify_min.currentText()),
            "auto_cancel": self.auto_cancel.isChecked(),
            "priority_mode": p_mode,
            "preferred_seats": all_prefs,
        }
