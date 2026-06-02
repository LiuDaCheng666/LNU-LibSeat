"""主窗口 — 现代左右分栏 + 磨砂标题栏 + 状态栏 + 主题切换"""
import sys
from datetime import datetime, timedelta, timezone
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QTextBrowser, QVBoxLayout, QWidget,
)
from .theme import (
    C, sans, mono, frosted_shadow, soft_glow, RADIUS_SM,
    current_theme, detect_os_theme, set_theme,
)
from .config_store import save_config, load_config
from .panels.config_panel import ConfigPanel
from .panels.log_panel import LogPanel
from .runtime_state import load_single_runtime_state
from .workers.alloc_worker import AllocWorker


def _bj_now():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ── 主题：优先读取已保存偏好，否则跟随系统 ──
        saved = load_config()
        self._saved_config = dict(saved)
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

        self.config_panel.action_bar.start_clicked.connect(self._on_start)
        self.config_panel.action_bar.stop_clicked.connect(self._on_stop)

        # 拖拽窗口支持
        self._drag_pos = None
        self._start_time = None
        self._pulse_timer = None

        # 加载已保存的配置
        self.config_panel.apply_config(saved)

        # 初始日志
        self.log_panel.log(f"  LibSeat Allocator v1.0.0\n", C.TERM_ACCENT)
        theme_text = "暗色" if current_theme() == "dark" else "亮色"
        self.log_panel.log(f"  {_bj_now().strftime('%Y-%m-%d %H:%M:%S')}   系统就绪  |  主题: {theme_text}\n\n", C.TERM_GREEN)
        if not saved.get("first_launch_help_shown", False):
            QTimer.singleShot(500, self._show_first_launch_help)

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
        return f"""
        <html>
        <body style="font-family:'Microsoft YaHei UI','Segoe UI',sans-serif; font-size:13px; color:{C.TEXT}; line-height:1.6;">
          <h2 style="margin:0 0 8px 0; color:{C.ACCENT};">LibSeat Allocator 使用帮助</h2>
          <p>这个工具用于按你的账号、校区、房间和时间段，自动寻找并预约图书馆座位。当前主要支持三种使用方式：</p>

          <h3>1. 普通预约</h3>
          <p>填写第一个账号，选择校区、房间和目标时间，点击开始。程序会先用 API 扫描可用座位，给出推荐方案，确认后自动完成预约。</p>
          <p><b>例子：</b>想预约 09:00 到 12:00 的二楼书库北座位，就把时间设为 09:00-12:00，模式可保持单账号逐段或按需要选择。</p>

          <h3>2. 单账号逐段预约</h3>
          <p>适合想覆盖一大段连续学习时间，但系统单次预约时长有限或没有一个座位能连续覆盖全天的情况。</p>
          <p><b>例子：</b>你想从 09:00 坐到 21:00。程序先预约第一段，例如 09:00-14:00；如果设置提前 30 分钟，就会在 13:30 开始查找 14:00 之后的下一段座位。找到后会弹窗展示下一段座位、房间和时间。你确认后，程序会取消当前预约并预约新座位。</p>
          <p>如果勾选“自动取消并换座”，找到下一段后会跳过确认直接执行。此功能正在进行测试，使用此功能请不要随意关闭软件。</p>
          <p>尽管已经做了保存和继承，但是为了稳定，使用多段单账号预约尽可能保留此软件运行</p>

          <h3>3. 多账号分时段</h3>
          <p>适合多个账号分别承担不同时间段。程序会先规划分段方案，确认后依次登录账号预约对应时段。</p>
          <p><b>例子：</b>账号 A 预约 09:00-13:00，账号 B 预约 13:00-17:00，账号 C 预约 17:00-21:00。</p>

          <h3>重要选项</h3>
          <ul>
            <li><b>跨房间搜索：</b>目标房间没有合适座位时，可扫描你勾选的其他房间。</li>
            <li><b>优先座位：</b>填写常用座位号后，可以选择“优先座位优先”。如果优先座位不可用，会回退到可用的较长时段。</li>
            <li><b>测试模式：</b>只扫描并生成方案，不执行预约、取消或换座。调试配置时建议先用它。</li>
            <li><b>主题切换：</b>右上角月亮/太阳按钮可以切换亮色和暗色主题。主题切换需要重启应用才能完全生效。</li>
          </ul>

          <h3>关闭和恢复</h3>
          <p>单账号逐段运行时，如果不小心关闭程序，程序会先尝试保存当前预约、下一次扫描时间和已找到的下一段推荐。下次启动并登录后，会查询“我的预约”，再询问你是否继续上次计划、重新扫描或停止。</p>

          <h3>注意事项</h3>
          <ul>
            <li>请确认账号密码、校区、房间和时间段填写正确。点击开始后将会完全自动执行，不要点击其他操作</li>
            <li>右上角小太阳或月亮可以切换主题，重启生效</li>
            <li>运行期间尽量不要手动操作自动打开的浏览器窗口，避免页面状态和程序判断不一致。跨房间选多个房间计算时间会拉长</li>
            <li>换座流程是先确认下一段推荐，再取消当前预约并预约新座位。遇到网络慢、验证码失败或座位被抢，程序会在日志里显示失败原因。</li>
            <li>遇到任何页面或者问题请第一时间联系上报</li>
          </ul>

          <p style="color:{C.TEXT_MUTED};">你可以随时点击窗口右上角的 ? 按钮再次打开本帮助。</p>
        </body>
        </html>
        """

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
        ver = QLabel("v1.0.0")
        ver.setFont(sans(8))
        ver.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        sl.addWidget(ver)
        return bar

    # ──────── 动作 ────────
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
        self.log_panel.log(f"  LibSeat Allocator v1.0.0\n", C.TERM_ACCENT)
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

    def _on_log(self, text, color):
        self.log_panel.log(text, color)

    def _on_finished(self):
        self.config_panel.action_bar.set_running(False)
        self.log_panel.log(f"\n  {_bj_now().strftime('%H:%M:%S')}   结束\n", C.TERM_LINE_NUM)
        self._start_time = None
        self.runtime_label.setText("")

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
