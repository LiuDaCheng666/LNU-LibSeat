"""主窗口 — 现代左右分栏 + 磨砂标题栏 + 状态栏 + 主题切换"""
import sys
from datetime import datetime, timedelta, timezone
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QMainWindow,
    QMessageBox, QPushButton, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)
from .theme import (
    C, sans, mono, frosted_shadow, soft_glow, RADIUS_SM,
    current_theme, detect_os_theme, set_theme,
)
from .config_store import save_config, load_config
from .panels.config_panel import ConfigPanel
from .panels.log_panel import LogPanel
from .runtime_state import clear_single_runtime_state, load_single_runtime_state
from .workers.alloc_worker import AllocWorker
from .widgets.animated_frame import set_low_animation_mode

APP_VERSION = "v2.6.0"


def _bj_now():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ── 主题：优先读取已保存偏好，否则跟随系统 ──
        saved = load_config()
        self._saved_config = dict(saved)
        self._low_animation_enabled = bool(saved.get("low_animation", False))
        set_low_animation_mode(self._low_animation_enabled)
        saved_theme = saved.get("theme", "auto")
        if saved_theme in ("light", "dark"):
            set_theme(saved_theme)
        else:
            set_theme(detect_os_theme())
        self._current_theme = current_theme()

        self.setWindowTitle("LibSeat Allocator")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)

        central = QWidget()
        central.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {C.BG_TOP},
                stop:1 {C.BG_BOTTOM});
        """)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 标题栏（磨砂）──
        outer.addWidget(self._title_bar())

        # ── 主体左右分栏 ──
        body = QHBoxLayout()
        body.setContentsMargins(22, 18, 22, 14)
        body.setSpacing(22)

        self.config_panel = ConfigPanel()
        body.addWidget(self.config_panel, stretch=40)

        self.log_panel = LogPanel()
        body.addWidget(self.log_panel, stretch=60)

        outer.addLayout(body, stretch=1)

        # ── 状态栏（磨砂）──
        outer.addWidget(self._status_bar())

        # ── Worker ──
        self.worker = AllocWorker(self)
        self.worker.log_line.connect(self._on_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.status_changed.connect(self._on_status)
        self.worker.plan_status_changed.connect(self._on_plan_status)
        self.worker.selection_requested.connect(self._on_selection_requested)

        self.config_panel.action_bar.start_clicked.connect(self._on_start)
        self.config_panel.action_bar.stop_clicked.connect(self._on_stop)

        # 拖拽窗口支持
        self._drag_pos = None
        self._start_time = None
        self._pulse_timer = None
        self._plan_status = {}
        self._active_selection_dialog = None
        self._plan_timer = QTimer(self)
        self._plan_timer.timeout.connect(self._refresh_plan_countdown)
        self._plan_timer.start(1000)

        # 加载已保存的配置
        self.config_panel.apply_config(saved)

        # 初始日志
        self.log_panel.log(f"  LibSeat Allocator {APP_VERSION}\n", C.TERM_ACCENT)
        theme_text = "暗色" if current_theme() == "dark" else "亮色"
        self.log_panel.log(f"  {_bj_now().strftime('%Y-%m-%d %H:%M:%S')}   系统就绪  |  主题: {theme_text}\n\n", C.TERM_GREEN)
        if not saved.get("first_launch_help_shown", False):
            QTimer.singleShot(500, self._show_first_launch_help)
        QTimer.singleShot(900, self._show_startup_recovery_prompt)

    # ═══════════════════════════════════
    #  拖拽窗口（标题栏）
    # ═══════════════════════════════════
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ──────── 标题栏 ────────
    def _title_bar(self):
        bar = QWidget()
        bar.setFixedHeight(46)
        bar.setStyleSheet(f"""
            background: {C.BAR_BG};
            border-bottom: 1px solid {C.BORDER_LIGHT};
        """)
        bar.setGraphicsEffect(frosted_shadow(bar))

        tl = QHBoxLayout(bar)
        tl.setContentsMargins(18, 0, 8, 0)
        tl.setSpacing(0)

        # Logo + 标题
        title = QLabel("  ▣  LibSeat Allocator")
        title.setFont(sans(13, bold=True))
        title.setStyleSheet(f"color: {C.ACCENT}; background: transparent; padding-right: 12px;")
        tl.addWidget(title)
        tl.addStretch(1)

        # 帮助按钮
        self.help_btn = QPushButton("?")
        self.help_btn.setFont(sans(12, bold=True))
        self.help_btn.setFixedSize(38, 28)
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.setFlat(True)
        self.help_btn.setToolTip("打开使用帮助")
        self.help_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_MUTED};
                background: transparent;
                border: none;
                border-radius: {RADIUS_SM}px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {C.ACCENT};
                background: {C.GRAY_300};
            }}
        """)
        self.help_btn.clicked.connect(self._show_help_dialog)
        tl.addWidget(self.help_btn)

        # 主题切换按钮
        self.theme_btn = QPushButton()
        self.theme_btn.setFont(sans(11))
        self.theme_btn.setFixedSize(38, 28)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setFlat(True)
        self._refresh_theme_btn_icon()
        self.theme_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_MUTED};
                background: transparent;
                border: none;
                border-radius: {RADIUS_SM}px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {C.WARN};
                background: {C.GRAY_300};
            }}
        """)
        self.theme_btn.clicked.connect(self._on_toggle_theme)
        tl.addWidget(self.theme_btn)

        self.low_anim_btn = QPushButton()
        self.low_anim_btn.setFont(sans(9, bold=True))
        self.low_anim_btn.setFixedSize(38, 28)
        self.low_anim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.low_anim_btn.setFlat(True)
        self._refresh_low_animation_btn()
        self.low_anim_btn.clicked.connect(self._on_toggle_low_animation)
        tl.addWidget(self.low_anim_btn)

        # 窗口控制按钮 — 使用 QPushButton 以获得更好的 hover 效果
        for icon, action, hover_color in [
            ("─", "min", C.ACCENT),
            ("□", "max", C.SUCCESS),
            ("✕", "close", C.ERR),
        ]:
            btn = QPushButton(icon)
            btn.setFont(sans(12))
            btn.setFixedSize(38, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {C.TEXT_MUTED};
                    background: transparent;
                    border: none;
                    border-radius: {RADIUS_SM}px;
                    padding: 0;
                }}
                QPushButton:hover {{
                    color: {hover_color};
                    background: {C.GRAY_300};
                }}
            """)

            if action == "close":
                btn.clicked.connect(self.close)
            elif action == "min":
                btn.clicked.connect(self.showMinimized)
            elif action == "max":
                btn.clicked.connect(lambda: (
                    self.showNormal() if self.isMaximized() else self.showMaximized()
                ))

            tl.addWidget(btn)

        return bar

    def _refresh_theme_btn_icon(self):
        """根据当前主题更新按钮图标"""
        if current_theme() == "dark":
            self.theme_btn.setText("☀")
            self.theme_btn.setToolTip("切换为亮色主题")
        else:
            self.theme_btn.setText("☾")
            self.theme_btn.setToolTip("切换为暗色主题")

    def _refresh_low_animation_btn(self):
        if self._low_animation_enabled:
            text = "低"
            color = C.SUCCESS
            hover_color = C.SUCCESS
            bg = C.ACCENT_SOFT
            tooltip = "低动画模式已开启：动态渐变已暂停，点击恢复动画"
        else:
            text = "动"
            color = C.TEXT_MUTED
            hover_color = C.ACCENT
            bg = "transparent"
            tooltip = "点击开启低动画模式：暂停动态渐变以降低占用"

        self.low_anim_btn.setText(text)
        self.low_anim_btn.setToolTip(tooltip)
        self.low_anim_btn.setStyleSheet(f"""
            QPushButton {{
                color: {color};
                background: {bg};
                border: none;
                border-radius: {RADIUS_SM}px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {hover_color};
                background: {C.GRAY_300};
            }}
        """)

    def _on_toggle_low_animation(self):
        self._low_animation_enabled = not self._low_animation_enabled
        set_low_animation_mode(self._low_animation_enabled)
        self._refresh_low_animation_btn()

        cfg = self._collect_config_for_save()
        cfg["low_animation"] = self._low_animation_enabled
        self._save_config(cfg)

        if hasattr(self, "log_panel"):
            if self._low_animation_enabled:
                self.log_panel.log("  低动画模式已开启：动态渐变已暂停，以降低空闲占用。\n", C.TERM_GREEN)
            else:
                self.log_panel.log("  低动画模式已关闭：动态渐变已恢复。\n", C.TERM_YELLOW)

    def _on_toggle_theme(self):
        """切换主题：保存偏好 → 弹窗提示用户手动重启"""
        new_theme = "dark" if current_theme() == "light" else "light"
        new_label = "暗色" if new_theme == "dark" else "亮色"

        # 保存配置（含主题偏好）
        cfg = self._collect_config_for_save()
        cfg["theme"] = new_theme
        self._save_config(cfg)

        # 弹窗确认
        msg = QMessageBox(self)
        msg.setWindowTitle("主题切换")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(f"即将切换为 <b>{new_label}</b> 主题")
        msg.setInformativeText(
            "主题变更需要重启应用才能完全生效。\n\n"
            "点击「确定」将关闭当前应用，\n请稍后手动重新启动。"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Ok)
        # 翻译按钮文字
        msg.button(QMessageBox.StandardButton.Ok).setText("确定并关闭")
        msg.button(QMessageBox.StandardButton.Cancel).setText("取消")

        if msg.exec() == QMessageBox.StandardButton.Ok:
            # 标记：closeEvent 不再重复保存（避免覆盖已写入的主题偏好）
            self._closing_for_theme_switch = True
            self.close()

    def _help_html(self):
        return f”””
        <html>
        <body style=”font-family:'Microsoft YaHei UI','Segoe UI',sans-serif; font-size:13px; color:{C.TEXT}; line-height:1.6;”>
          <h2 style=”margin:0 0 8px 0; color:{C.ACCENT};”>LibSeat Allocator {APP_VERSION} 使用帮助</h2>
          <p>这个工具用于按你的账号、校区、房间和时间段，先用 API 快速扫描可用座位，再让你从候选列表或整套方案中选择，最后自动完成真实预约。</p>

          <h3>1. 快速上手：普通预约</h3>
          <p>填写第一个账号，选择校区、房间和目标时间，点击<b>”开始”</b>。程序会先用 API 扫描可用座位，弹窗列出候选，你选择后自动打开浏览器完成预约。</p>
          <p><b>例子：</b>想预约 09:00 到 12:00，就把时间设为 09:00-12:00。第一次使用建议<b>先开启”测试模式”</b>，确认候选合理后再关闭测试模式执行真实预约。</p>

          <h3>2. 单账号逐段预约（长时间学习）</h3>
          <p>适合想覆盖一大段连续学习时间（如 09:00-21:00），但系统单次预约时长有限，或没有一个座位能连续覆盖全天的情况。</p>
          <p><b>例子：</b>程序先预约第一段，例如 09:00-14:00。第一段成功后，右侧日志上方会出现<b>”续约计划”</b>，显示下一次扫描时间和倒计时。若设置提前 30 分钟，就会在 13:30 自动重新扫描 14:00 之后的下一段。</p>
          <p>找到下一段后，程序会弹窗列出候选座位供你选择。你确认后，程序先取消当前预约，再预约新座位。后续预案只是参考，真正换座前会重新扫描确认。</p>
          <p>如果勾选<b>”自动取消并换座”</b>，找到下一段后会跳过确认直接执行。<b>第一次使用不建议开启</b>自动模式，先用弹窗确认熟悉流程。</p>

          <h3>3. 多账号分时段</h3>
          <p>适合用多个账号分别覆盖不同时间段。程序会先生成最多 50 套候选方案，你可以在列表中筛选排序后选择一套，再依次登录账号预约对应时段。</p>
          <p><b>例子：</b>方案一可能只用账号 A 预约 09:00-15:00；方案二可能是账号 A 预约 09:00-11:00、账号 B 预约 11:00-15:00。账号不必用满，程序会给出多种组合供你选择。</p>
          <p>多账号方案弹窗支持<b>按完整覆盖、当前房间、账号数量、缺口</b>筛选排序，请浏览后再选择，不必只接受第一条推荐。</p>

          <h3>4. API 扫描进度和并发（v2.6.0 新增）</h3>
          <p>扫描时会弹出<b>双进度条窗口</b>：</p>
          <ul>
            <li><b>上方进度条：</b>总体房间扫描进度，看到第几个房间、共几个房间。</li>
            <li><b>下方进度条：</b>当前房间的座位扫描进度，看到已经扫了多少座位、还剩多少。</li>
          </ul>
          <p>进度条变化时说明程序正在等待 API 返回数据，<b>不需要手动点击浏览器</b>。有了进度条你再也不用面对静止的浏览器不知所措了。</p>
          <p>高级设置里的<b>”API 并发”</b>控制同时扫描的座位数量：</p>
          <ul>
            <li><b>1</b> — 逐个扫描，速度最慢但对网络压力最小，适合排查问题。</li>
            <li><b>5</b> — 较稳妥，适合网络一般或频繁超时的情况。</li>
            <li><b>10（默认）</b> — 速度和稳定性比较均衡，推荐日常使用。</li>
            <li><b>15 / 20</b> — 更激进，可能更快完成扫描，但更容易触发网络超时，部分座位数据可能拿不到。</li>
          </ul>

          <h3>5. 为什么个别座位还是会超时？</h3>
          <p>即使优化后，你仍可能看到扫描末尾有几个座位超时。这是因为部分房间里存在<b>显示不可用的座位</b>——可能是临时损坏、社团专用或其他特殊状态。这些座位无法确认是否会恢复，所以程序没法把它们永久排除在外，只能硬着头皮扫描，跳过当次超时并继续生成方案。这<b>不是程序卡死</b>，进度条会继续前进。</p>

          <h3>重要选项说明</h3>
          <ul>
            <li><b>跨房间搜索：</b>默认关闭。开启后勾选你愿意去的其他房间；勾选越多，API 请求越多，等待越久。弹窗会同时展示当前房间、全局最佳和勾选房间的候选。</li>
            <li><b>优先座位：</b>填写常用座位号后，可以选择”优先座位优先”策略。如果优先座位不可用，会回退到可用时间更长的座位。</li>
            <li><b>测试模式：</b>只扫描生成候选/方案，不执行真实预约、取消或换座。单账号测试模式会显示续约预览，但不会保存为可恢复任务。<b>第一次使用请一定先开测试模式！</b></li>
            <li><b>主题切换：</b>右上角月亮/太阳按钮可切换亮色和暗色主题。主题切换需要重启应用才能完全生效。</li>
            <li><b>低动画模式：</b>右上角”动/低”按钮可暂停动态渐变背景，保留静态视觉效果，同时降低窗口可见时的 CPU 占用。再次点击恢复动画。</li>
          </ul>

          <h3>关闭和恢复</h3>
          <p>单账号真实逐段运行时，如果不小心关闭程序，程序会先保存当前预约、下一次扫描计划和后续预案。下次打开软件会先弹窗展示关闭前的续约计划，你可以选择<b>”继续计划”</b>或<b>”不管”</b>。</p>
          <p>选择继续后，程序会登录并查询服务器”我的预约”；如果服务器仍有有效预约，再询问继续上次计划、重新扫描或停止。选择不管<b>只清理本地提示，不会取消服务器预约</b>，你的座位仍然有效。</p>

          <h3>注意事项</h3>
          <ul>
            <li>请确认账号密码、校区、房间和时间段填写正确。真实模式会执行预约、取消和换座操作。</li>
            <li>第一次配置<b>务必先开启测试模式</b>，确认候选和方案合理后再真实运行。</li>
            <li>运行期间<b>不要手动操作</b>自动打开的浏览器窗口，避免页面状态和程序判断不一致。</li>
            <li>单账号/多账号模式切换后，建议重启一次程序确保界面与实际模式一致。</li>
            <li>换座流程是先确认下一段推荐，再取消当前预约并预约新座位。遇到网络慢、验证码失败或座位被抢，程序会在日志里显示失败原因。</li>
            <li>遇到页面结构变化或异常提示，请保留日志并反馈。</li>
          </ul>

          <p style=”color:{C.TEXT_MUTED};”>你可以随时点击窗口右上角的 <b>?</b> 按钮再次打开本帮助；如果窗口打开时 CPU 占用偏高，可以点击”动”切换到低动画模式。</p>
        </body>
        </html>
        “””

    def _show_help_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("使用帮助")
        dlg.resize(760, 620)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: {C.CARD};
            }}
            QTextBrowser {{
                background: {C.INPUT};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: {RADIUS_SM}px;
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._help_html())
        layout.addWidget(browser, stretch=1)

        row = QHBoxLayout()
        row.addStretch(1)
        ok_btn = QPushButton("我知道了")
        ok_btn.setFont(sans(10, bold=True))
        ok_btn.setMinimumHeight(34)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_INVERT};
                background: {C.ACCENT};
                border: none;
                border-radius: {RADIUS_SM}px;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background: {C.ACCENT_HOT};
            }}
        """)
        ok_btn.clicked.connect(dlg.accept)
        row.addWidget(ok_btn)
        layout.addLayout(row)
        dlg.exec()

    def _show_first_launch_help(self):
        self._show_help_dialog()
        cfg = self._collect_config_for_save()
        cfg["first_launch_help_shown"] = True
        self._save_config(cfg)

    def _collect_config_for_save(self, base=None):
        cfg = dict(base or self.config_panel.collect())
        saved = getattr(self, "_saved_config", {}) or {}
        cfg["theme"] = saved.get("theme", "auto")
        cfg["low_animation"] = bool(getattr(self, "_low_animation_enabled", saved.get("low_animation", False)))
        cfg["first_launch_help_shown"] = bool(saved.get("first_launch_help_shown", False))
        return cfg

    def _save_config(self, cfg):
        ok = save_config(cfg)
        if ok:
            self._saved_config = dict(cfg)
        return ok

    # ──────── 状态栏 ────────
    def _status_bar(self):
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet(f"""
            background: {C.BAR_BG};
            border-top: 1px solid {C.BORDER_LIGHT};
        """)
        sl = QHBoxLayout(bar)
        sl.setContentsMargins(18, 0, 18, 0)
        sl.setSpacing(0)

        # 状态指示灯 + 文字
        self.status_dot = QLabel("●")
        self.status_dot.setFont(sans(10))
        self.status_dot.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        self.status_dot.setFixedWidth(18)

        self.status_label = QLabel("就 绪")
        self.status_label.setFont(sans(9))
        self.status_label.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
        sl.addWidget(self.status_dot)
        sl.addWidget(self.status_label)

        sl.addStretch(1)

        # 运行时长
        self.runtime_label = QLabel("")
        self.runtime_label.setFont(sans(8))
        self.runtime_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        sl.addWidget(self.runtime_label)

        sl.addSpacing(20)

        # 版本号
        ver = QLabel(APP_VERSION)
        ver.setFont(sans(8))
        ver.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        sl.addWidget(ver)
        return bar

    # ──────── 动作 ────────
    def _format_saved_plan_summary(self, state):
        current = state.get("current_booking") or {}
        pending = state.get("pending_next_slot") or {}
        upcoming = state.get("upcoming_slots") or []
        config = state.get("config") or {}
        target_range = state.get("target_range") or f"{config.get('day_start', '')}-{config.get('day_end', '')}"
        lines = [
            f"保存时间: {state.get('saved_at_bj', '未知')}",
            f"目标时段: {target_range}",
            f"下一次扫描: {state.get('notify_at') or '按当前预约结束时间重新计算'}",
        ]
        if current:
            lines.append(
                "当前预约: "
                f"{current.get('room_name') or '未知房间'} / 座位{current.get('seat_num') or '?'} / "
                f"{current.get('start_time') or '?'}-{current.get('end_time') or '?'}"
            )
        if pending:
            lines.append(
                "关闭前下一段: "
                f"{pending.get('room_name') or '未知房间'} / 座位{pending.get('seat_num') or '?'} / "
                f"{pending.get('start') or '?'}-{pending.get('end') or '?'}"
            )
        elif upcoming:
            lines.append("关闭前后续预案:")
            for idx, slot in enumerate(upcoming[:3], start=1):
                lines.append(
                    f"  第{idx}段预案: {slot.get('room_name') or '未知房间'} / "
                    f"座位{slot.get('seat_num') or '?'} / {slot.get('start') or '?'}-{slot.get('end') or '?'}"
                )
        return "\n".join(lines)

    def _resume_config_from_state(self, state):
        cfg = self._collect_config_for_save()
        saved_cfg = state.get("config") or {}
        for key in (
            "campus",
            "room",
            "day_start",
            "day_end",
            "cross_room",
            "cross_room_rooms",
            "preferred_seats",
            "priority_mode",
            "cross_room_min_gain_minutes",
            "api_report_include_intervals",
            "api_scan_workers",
            "pre_notify",
            "auto_cancel",
            "notify_timeout",
        ):
            if key in saved_cfg:
                cfg[key] = saved_cfg[key]
        cfg["mode"] = "single"
        cfg["dry_run"] = False
        return cfg

    def _show_startup_recovery_prompt(self):
        if self.worker.is_running():
            return
        state = load_single_runtime_state()
        if not (state.get("active") and state.get("mode") == "single"):
            return
        if state.get("dry_run") or state.get("phase") == "dry_run_preview":
            return

        current_cfg = self._collect_config_for_save()
        state_account = str(state.get("account", "")).strip()
        current_account = str((current_cfg.get("accounts") or [[""]])[0][0]).strip()
        if state_account and current_account and state_account != current_account:
            self.log_panel.log(
                "  检测到单账号恢复状态，但账号与当前第一个账号不一致，未自动提示。\n",
                C.WARN,
            )
            return

        self._on_plan_status(state)
        msg = QMessageBox(self)
        msg.setWindowTitle("检测到关闭前的单账号续约计划")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("读取到上次关闭前保存的单账号逐段预约计划。")
        msg.setInformativeText(
            self._format_saved_plan_summary(state)
            + "\n\n继续计划会登录并查询服务器当前预约，再接管倒计时/换座流程。\n"
            + "不管则只清理本地恢复提示，不会取消服务器上的已有预约。"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.button(QMessageBox.StandardButton.Yes).setText("继续计划")
        msg.button(QMessageBox.StandardButton.No).setText("不管")

        if msg.exec() == QMessageBox.StandardButton.Yes:
            cfg = self._resume_config_from_state(state)
            self.config_panel.apply_config(cfg)
            self._save_config(cfg)
            self.log_panel.log("  用户选择继续关闭前的单账号续约计划，准备登录验证当前预约。\n", C.TERM_GREEN)
            QTimer.singleShot(0, self._on_start)
        else:
            clear_single_runtime_state()
            self._on_plan_status({})
            self.log_panel.log("  已忽略关闭前的单账号续约计划；服务器已有预约不会被取消。\n", C.WARN)

    def _on_start(self):
        cfg = self._collect_config_for_save()
        if not cfg["accounts"]:
            self.log_panel.log("[ERROR] 请至少填写一个账号\n", C.ERR)
            return
        # 启动时自动保存配置
        self._save_config(cfg)

        has_resume_state = False
        if cfg.get("mode") == "single":
            runtime_state = load_single_runtime_state()
            state_account = str(runtime_state.get("account", "")).strip()
            current_account = str(cfg["accounts"][0][0]).strip() if cfg.get("accounts") else ""
            if (
                runtime_state.get("active")
                and runtime_state.get("mode") == "single"
                and (not state_account or state_account == current_account)
            ):
                cfg = dict(cfg)
                cfg["resume_single_state"] = runtime_state
                has_resume_state = True

        self.log_panel.clear()
        self._on_plan_status({})
        self.log_panel.log(f"  LibSeat Allocator {APP_VERSION}\n", C.TERM_ACCENT)
        self.log_panel.log(f"  {_bj_now().strftime('%Y-%m-%d %H:%M:%S')}   开始分配\n", C.TERM_YELLOW)
        acc_count = len(cfg["accounts"])
        mode_text = "多账号分时段" if cfg["mode"] == "multi" else "单账号逐段"
        self.log_panel.log(f"  账号: {acc_count}  |  模式: {mode_text}\n\n", C.TERM_TEXT)
        if has_resume_state:
            self.log_panel.log("  检测到上次单账号运行状态，将在登录后查询并询问是否恢复\n\n", C.TERM_YELLOW)
        if cfg.get("dry_run", False):
            self.log_panel.log("  测试模式: 仅 API 抓取并生成方案，不执行预约\n\n", C.TERM_GREEN)
        self.config_panel.action_bar.set_running(True)
        self._start_time = _bj_now()
        self.worker.start(cfg)

    def _on_stop(self):
        self.log_panel.log("\n[STOP] 正在停止...\n", C.WARN)
        self.worker.stop()
        if self._active_selection_dialog is not None:
            self._active_selection_dialog.reject()

    def _selection_metrics(self, item):
        return item.get("metrics", {}) or {}

    def _selection_filter_options(self, kind):
        if kind == "schedule":
            return ["全部", "完整覆盖", "当前房间", "单账号整段", "跨房间", "有缺口"]
        if kind == "seat":
            return ["全部", "推荐", "当前房间"]
        return ["全部"]

    def _selection_sort_options(self, kind):
        if kind == "schedule":
            return ["推荐排序", "时间最长", "缺口最少", "当前房间优先", "账号最少"]
        if kind == "seat":
            return ["推荐排序", "时间最长", "当前房间优先"]
        return ["推荐排序"]

    def _selection_filter_match(self, item, kind, mode):
        if mode == "全部":
            return True
        if kind == "schedule":
            metrics = self._selection_metrics(item)
            if mode == "完整覆盖":
                return bool(metrics.get("full_cover"))
            if mode == "当前房间":
                return bool(metrics.get("all_target_room"))
            if mode == "单账号整段":
                return bool(metrics.get("full_cover")) and int(metrics.get("segment_count", 0) or 0) == 1
            if mode == "跨房间":
                return int(metrics.get("cross_room_segments", 0) or 0) > 0
            if mode == "有缺口":
                return int(metrics.get("gap_minutes", 0) or 0) > 0
        if kind == "seat":
            if mode == "推荐":
                return bool(item.get("is_recommended"))
            if mode == "当前房间":
                return str(item.get("target_room", "")) and str(item.get("room_name", "")) == str(item.get("target_room", ""))
        return True

    def _selection_sort_key(self, item, kind, mode, original_index):
        if kind == "schedule":
            metrics = self._selection_metrics(item)
            covered = int(metrics.get("covered_minutes", 0) or 0)
            gap = int(metrics.get("gap_minutes", 0) or 0)
            segments = int(metrics.get("segment_count", 0) or 0)
            current = bool(metrics.get("all_target_room"))
            full = bool(metrics.get("full_cover"))
            if mode == "时间最长":
                return (-covered, gap, 0 if current else 1, segments, original_index)
            if mode == "缺口最少":
                return (gap, -covered, 0 if current else 1, segments, original_index)
            if mode == "当前房间优先":
                return (0 if current else 1, 0 if full else 1, -covered, gap, segments, original_index)
            if mode == "账号最少":
                return (segments, 0 if full else 1, -covered, gap, original_index)
        if kind == "seat":
            duration = int(item.get("duration_minutes", 0) or 0)
            current = str(item.get("target_room", "")) and str(item.get("room_name", "")) == str(item.get("target_room", ""))
            recommended = bool(item.get("is_recommended"))
            if mode == "时间最长":
                return (-duration, 0 if recommended else 1, original_index)
            if mode == "当前房间优先":
                return (0 if current else 1, -duration, 0 if recommended else 1, original_index)
        return (original_index,)

    def _selection_line(self, index, item, kind):
        if kind == "schedule":
            metrics = self._selection_metrics(item)
            tags = " ".join(f"[{tag}]" for tag in (item.get("tags") or []))
            return (
                f"方案{index} {tags}  覆盖 {metrics.get('covered_minutes', 0)}/"
                f"{metrics.get('desired_minutes', 0)} 分钟 | {metrics.get('segment_count', 0)} 个账号 | "
                f"缺口 {metrics.get('gap_minutes', 0)} 分钟 | 换房 {metrics.get('room_changes', 0)} 次"
            )
        marker = " ★" if item.get("is_recommended") else ""
        return (
            f"候选{index}{marker}  {item.get('title', '候选座位')} | "
            f"{item.get('room_name')} / 座位{item.get('seat_num')} | "
            f"{item.get('start')}-{item.get('end')} | {item.get('duration_minutes', 0)} 分钟"
        )

    def _selection_detail(self, index, item, kind):
        if kind == "schedule":
            schedule = item.get("schedule", {}) or {}
            metrics = self._selection_metrics(item)
            tags = " ".join(f"[{tag}]" for tag in (item.get("tags") or []))
            lines = [
                f"方案{index} {tags}".strip(),
                f"类型: {item.get('title', '')}",
                f"覆盖: {metrics.get('covered_minutes', 0)}/{metrics.get('desired_minutes', 0)} 分钟",
                f"账号: {metrics.get('segment_count', 0)} 个    缺口: {metrics.get('gap_minutes', 0)} 分钟    换房: {metrics.get('room_changes', 0)} 次",
            ]
            note = item.get("note")
            if note:
                lines.append(f"说明: {note}")
            if (
                int(metrics.get("covered_minutes", 0) or 0) < int(metrics.get("desired_minutes", 0) or 0)
                and int(metrics.get("gap_minutes", 0) or 0) == 0
            ):
                lines.append("开始前等待时间未计入缺口，列表仍会按实际覆盖时长排序。")
            pool_count = item.get("candidate_pool_count")
            if pool_count:
                lines.append(f"已生成 {pool_count} 套候选，当前列表最多显示 50 套。")
            lines.append("")
            for seg_idx, seg in enumerate(schedule.get("segments", []) or [], start=1):
                lines.append(
                    f"账号{seg_idx}: {seg.get('room_name')} / 座位{seg.get('seat_num')} / "
                    f"{seg.get('start')}-{seg.get('end')} / {seg.get('duration_minutes')} 分钟"
                )
                if seg.get("decision_note"):
                    lines.append(f"  {seg.get('decision_note')}")
            gaps = schedule.get("gaps", []) or []
            if gaps:
                lines.append("")
                lines.append("未覆盖时段:")
                for gap in gaps:
                    lines.append(f"  {gap.get('start')}-{gap.get('end')}")
            return "\n".join(lines)

        lines = [
            f"候选{index}" + (" ★ 推荐" if item.get("is_recommended") else ""),
            f"房间: {item.get('room_name')}",
            f"座位: {item.get('seat_num')}",
            f"时间: {item.get('start')}-{item.get('end')} ({item.get('duration_minutes', 0)} 分钟)",
        ]
        if item.get("reason"):
            lines.append(f"说明: {item.get('reason')}")
        return "\n".join(lines)

    def _on_selection_requested(self, payload):
        request_id = str(payload.get("request_id", ""))
        try:
            choice = self._show_selection_dialog(payload)
        except Exception as exc:
            import traceback
            self.log_panel.log(
                f"\n[ERROR] 方案选择弹窗创建失败: {type(exc).__name__}: {exc}\n{traceback.format_exc()}\n",
                C.TERM_RED,
            )
            choice = str(payload.get("default_choice", "abort"))
        self.worker.provide_selection_result(request_id, choice)

    def _show_selection_dialog(self, payload):
        kind = str(payload.get("kind", "schedule"))
        title = str(payload.get("title", "方案选择"))
        message = str(payload.get("message", ""))
        items = list(payload.get("items") or [])
        default_choice = str(payload.get("default_choice", "abort"))
        timeout_seconds = int(payload.get("timeout_seconds", 300) or 0)
        if not items:
            return default_choice

        dialog = QDialog(self)
        self._active_selection_dialog = dialog
        dialog.setWindowTitle(title)
        if not self.windowIcon().isNull():
            dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setFixedSize(980 if kind == "schedule" else 860, 700 if kind == "schedule" else 620)
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {C.GRAY_100};
                color: {C.TEXT};
            }}
            QLabel {{
                color: {C.TEXT};
                background: transparent;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            }}
            QComboBox, QListWidget, QTextEdit {{
                background: {C.INPUT};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: {RADIUS_SM}px;
                padding: 6px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                selection-background-color: {C.ACCENT};
                selection-color: #ffffff;
            }}
            QListWidget::item {{
                min-height: 26px;
                padding: 3px 6px;
            }}
            QPushButton {{
                background: {C.INPUT_HOVER};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: {RADIUS_SM}px;
                padding: 9px 18px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            }}
            QPushButton#primaryButton {{
                background: {C.ACCENT};
                color: #ffffff;
                border-color: {C.ACCENT};
                font-weight: 700;
            }}
            QPushButton#primaryButton:hover {{
                background: {C.ACCENT_HOT};
            }}
        """)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        header = QWidget()
        header.setStyleSheet(f"background:{C.FRAMED_BG}; border:1px solid {C.BORDER_ACCENT}; border-radius:{RADIUS_SM}px;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(16)

        icon_label = QLabel()
        icon_label.setFixedSize(76, 76)
        icon_pix = self.windowIcon().pixmap(72, 72)
        if not icon_pix.isNull():
            icon_label.setPixmap(icon_pix)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            icon_label.setText("座")
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet(f"color:{C.ACCENT}; font-size:30px; font-weight:700; background:transparent;")
        header_layout.addWidget(icon_label)

        header_text = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size:18px; font-weight:700; color:{C.TEXT}; background:transparent;")
        title_label.setWordWrap(True)
        msg_label = QLabel(message)
        msg_label.setStyleSheet(f"font-size:13px; color:{C.TEXT_SEC}; background:transparent; line-height:1.4;")
        msg_label.setWordWrap(True)
        header_text.addWidget(title_label)
        header_text.addWidget(msg_label)
        header_layout.addLayout(header_text, stretch=1)
        root.addWidget(header)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("筛选"))
        filter_box = QComboBox()
        filter_box.addItems(self._selection_filter_options(kind))
        controls.addWidget(filter_box)
        controls.addWidget(QLabel("排序"))
        sort_box = QComboBox()
        sort_box.addItems(self._selection_sort_options(kind))
        controls.addWidget(sort_box)
        controls.addStretch(1)
        count_label = QLabel()
        count_label.setStyleSheet(f"color:{C.TEXT_MUTED};")
        controls.addWidget(count_label)
        root.addLayout(controls)

        list_widget = QListWidget()
        list_widget.setUniformItemSizes(True)
        list_widget.setMinimumHeight(190 if kind == "schedule" else 160)
        root.addWidget(list_widget, stretch=4)

        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setMinimumHeight(180)
        root.addWidget(detail, stretch=5)

        buttons = QHBoxLayout()
        confirm_btn = QPushButton("确定选择")
        confirm_btn.setObjectName("primaryButton")
        cancel_btn = QPushButton("取消")
        buttons.addWidget(confirm_btn)
        buttons.addWidget(cancel_btn)
        buttons.addStretch(1)
        root.addLayout(buttons)

        indexed_items = list(enumerate(items))
        visible_items = []
        choice = {"value": default_choice}

        def refresh_detail():
            row = list_widget.currentRow()
            if row < 0 or row >= len(visible_items):
                detail.setPlainText("没有符合当前筛选条件的方案。")
                return
            detail.setPlainText(self._selection_detail(row + 1, visible_items[row], kind))

        def rebuild_items():
            visible_items.clear()
            filtered = [
                (original_idx, item)
                for original_idx, item in indexed_items
                if self._selection_filter_match(item, kind, filter_box.currentText())
            ]
            filtered.sort(key=lambda pair: self._selection_sort_key(pair[1], kind, sort_box.currentText(), pair[0]))
            visible_items.extend(item for _idx, item in filtered)
            list_widget.clear()
            for index, item in enumerate(visible_items, start=1):
                list_widget.addItem(self._selection_line(index, item, kind))
            count_label.setText(f"{len(visible_items)}/{len(items)} 项")
            if visible_items:
                list_widget.setCurrentRow(0)
            refresh_detail()

        def accept_choice():
            row = list_widget.currentRow()
            if row < 0 or row >= len(visible_items):
                choice["value"] = default_choice
                dialog.reject()
                return
            choice["value"] = str(visible_items[row].get("option_id") or default_choice)
            dialog.accept()

        filter_box.currentTextChanged.connect(rebuild_items)
        sort_box.currentTextChanged.connect(rebuild_items)
        list_widget.currentRowChanged.connect(lambda _row: refresh_detail())
        list_widget.itemDoubleClicked.connect(lambda _item: accept_choice())
        confirm_btn.clicked.connect(accept_choice)
        cancel_btn.clicked.connect(dialog.reject)
        if timeout_seconds > 0:
            QTimer.singleShot(timeout_seconds * 1000, dialog.reject)

        rebuild_items()

        def bring_to_front():
            try:
                if self.isMinimized():
                    self.showNormal()
                self.raise_()
                self.activateWindow()
                dialog.raise_()
                dialog.activateWindow()
                QApplication.alert(dialog, 0)
            except Exception:
                pass

        bring_to_front()
        QTimer.singleShot(80, bring_to_front)
        QTimer.singleShot(300, bring_to_front)
        try:
            dialog.exec()
        finally:
            if self._active_selection_dialog is dialog:
                self._active_selection_dialog = None
        return choice["value"] if dialog.result() == QDialog.DialogCode.Accepted else default_choice

    def _on_log(self, text, color):
        self.log_panel.log(text, color)

    def _on_plan_status(self, payload):
        self._plan_status = dict(payload or {})
        self._refresh_plan_countdown()

    def _countdown_for_notify_at(self, notify_at):
        try:
            hh, mm = [int(part) for part in str(notify_at).split(":", 1)]
            now = _bj_now()
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            seconds = int((target - now).total_seconds())
            if seconds <= 0:
                return "即将扫描"
            h, rem = divmod(seconds, 3600)
            m, s = divmod(rem, 60)
            if h > 0:
                return f"{h}小时{m}分{s}秒"
            return f"{m}分{s}秒"
        except Exception:
            return "等待计算"

    def _refresh_plan_countdown(self):
        if not self._plan_status:
            self.log_panel.set_plan_status({})
            return
        payload = dict(self._plan_status)
        notify_at = payload.get("notify_at")
        if payload.get("active") and notify_at:
            payload["countdown"] = self._countdown_for_notify_at(notify_at)
        self.log_panel.set_plan_status(payload)

    def _on_finished(self):
        self.config_panel.action_bar.set_running(False)
        self.log_panel.log(f"\n  {_bj_now().strftime('%H:%M:%S')}   结束\n", C.TERM_LINE_NUM)
        self._start_time = None
        self.runtime_label.setText("")
        if self._plan_status.get("phase") != "dry_run_preview":
            self._on_plan_status({})

    def _on_status(self, status):
        if status == "running":
            self.status_dot.setStyleSheet(f"color: {C.ACCENT}; background: transparent; font-size: 11px;")
            self.status_label.setText("运 行 中")
            self.status_label.setStyleSheet(f"color: {C.ACCENT}; background: transparent;")
            # 启动运行时长更新
            self._update_runtime()
        elif status == "done":
            self.status_dot.setStyleSheet(f"color: {C.SUCCESS}; background: transparent;")
            self.status_label.setText("已 完 成")
            self.status_label.setStyleSheet(f"color: {C.SUCCESS}; background: transparent;")
            self.runtime_label.setText("")
        else:
            self.status_dot.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")
            self.status_label.setText("就 绪")
            self.status_label.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")

    def _update_runtime(self):
        if self._start_time:
            delta = _bj_now() - self._start_time
            h, r = divmod(int(delta.total_seconds()), 3600)
            m, s = divmod(r, 60)
            if h > 0:
                self.runtime_label.setText(f"运行 {h}h {m}m {s}s")
            else:
                self.runtime_label.setText(f"运行 {m}m {s}s")

        # 每10秒更新
        QTimer.singleShot(10000, self._update_runtime)

    # ──────── 关闭窗口时保存配置 ────────
    def closeEvent(self, event):
        # 主题切换关闭时跳过保存，避免覆盖已写入的主题偏好
        closing_for_theme = getattr(self, '_closing_for_theme_switch', False)
        cfg = self._collect_config_for_save()
        if not closing_for_theme:
            self._save_config(cfg)

        if self.worker.is_running():
            saved = self.worker.save_runtime_state("window_close")
            msg = QMessageBox(self)
            msg.setWindowTitle("任务仍在运行")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("当前预约任务仍在运行。")
            if cfg.get("mode") == "single":
                detail = "已尝试保存单账号自动换座恢复信息。"
                if not saved:
                    detail = "当前还没有可恢复的单账号预约状态。"
                msg.setInformativeText(
                    f"{detail}\n\n"
                    "关闭程序会停止本次计时和自动换座。\n"
                    "下次启动并登录后，程序会查询当前预约并询问是否恢复。"
                )
            else:
                msg.setInformativeText("关闭程序会停止当前任务。确定要退出吗？")
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            msg.button(QMessageBox.StandardButton.Yes).setText("保存并退出")
            msg.button(QMessageBox.StandardButton.No).setText("继续运行")
            if msg.exec() != QMessageBox.StandardButton.Yes:
                if closing_for_theme:
                    self._closing_for_theme_switch = False
                event.ignore()
                return
            self.worker.stop()
        super().closeEvent(event)
