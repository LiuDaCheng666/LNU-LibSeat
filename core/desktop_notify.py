# core/desktop_notify.py
"""
桌面通知模块

用于单账号模式：在需要换座时弹窗通知用户确认。

支持：
  - tkinter 消息框（Windows/macOS/Linux 原生）
  - 日志记录（无GUI环境回退）
"""

import sys
import threading
import time
from core.logger import get_logger

logger = get_logger(__name__)


def _show_tkinter_confirm(title: str, message: str, timeout_seconds: int = 300) -> bool:
    """
    使用 tkinter 显示确认对话框。

    Args:
        title: 窗口标题
        message: 消息内容
        timeout_seconds: 超时秒数（超时自动选择「否」）

    Returns:
        True=用户确认, False=用户拒绝或超时
    """
    import tkinter as tk
    from tkinter import messagebox

    result = {"confirmed": False, "done": False}

    def _do_popup():
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        root.attributes("-topmost", True)  # 置顶
        try:
            answer = messagebox.askyesno(title, message)
            result["confirmed"] = answer is True
        finally:
            result["done"] = True
            try:
                root.destroy()
            except Exception:
                pass

    # 在主线程中运行 tkinter
    popup_thread = threading.Thread(target=_do_popup, daemon=True)
    popup_thread.start()

    # 等待用户操作或超时
    waited = 0
    while not result["done"] and waited < timeout_seconds:
        time.sleep(0.5)
        waited += 0.5

    if not result["done"]:
        logger.warning("⏰ 通知超时 (%d秒未响应)，自动选择「放弃」", timeout_seconds)
        return False

    return result["confirmed"]


def _show_win32_toast(title: str, message: str) -> bool:
    """
    尝试使用 Windows Toast 通知。
    需要 Windows 10+ 且安装了 win10toast 或 plyer。
    """
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=10, threaded=True)
        return True
    except ImportError:
        pass

    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
        return True
    except ImportError:
        pass

    return False


def notify_and_confirm(
    title: str,
    message: str,
    timeout_seconds: int = 300,
) -> bool:
    """
    桌面通知 + 确认弹窗。

    单账号模式核心交互：通知用户下一段座位信息，等待确认。

    Args:
        title: 通知标题，如 "🔔 换座提醒"
        message: 通知内容，包含座位号、时间段等信息
        timeout_seconds: 超时秒数

    Returns:
        True = 用户点击确认，执行换座
        False = 用户拒绝或超时
    """
    logger.info("🔔 ====== 桌面通知 ======")
    logger.info("📋 %s", title)
    for line in message.split("\n"):
        if line.strip():
            logger.info("   %s", line.strip())
    logger.info("🔔 ======================")

    # 尝试 Windows Toast（非阻塞）
    _show_win32_toast(title, message)

    # 弹窗确认（阻塞等待用户操作）
    confirmed = _show_tkinter_confirm(title, message, timeout_seconds)

    if confirmed:
        logger.info("✅ 用户确认换座")
    else:
        logger.info("❌ 用户拒绝换座或超时")

    return confirmed


def _show_tkinter_choice(
    title: str,
    message: str,
    choices: list,
    default_choice: str = "abort",
    timeout_seconds: int = 300,
) -> str:
    """
    Show a small topmost choice dialog.

    choices: list of (value, label) tuples.
    """
    import tkinter as tk

    result = {"choice": default_choice, "done": False}

    def _do_popup():
        root = tk.Tk()
        root.withdraw()

        win = tk.Toplevel(root)
        win.title(title)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(bg="#f4f4f4")

        body = tk.Frame(win, padx=18, pady=16, bg="#f4f4f4")
        body.pack(fill="both", expand=True)

        label = tk.Message(
            body,
            text=message,
            width=560,
            bg="#f4f4f4",
            fg="#111111",
            font=("Microsoft YaHei UI", 10),
        )
        label.pack(fill="x", pady=(0, 14))

        row = tk.Frame(body, bg="#f4f4f4")
        row.pack(fill="x")

        def choose(value: str):
            if result["done"]:
                return
            result["choice"] = value
            result["done"] = True
            try:
                win.destroy()
            finally:
                try:
                    root.destroy()
                except Exception:
                    pass

        for value, label_text in choices:
            btn = tk.Button(
                row,
                text=label_text,
                command=lambda v=value: choose(v),
                padx=10,
                pady=5,
                font=("Microsoft YaHei UI", 9),
            )
            btn.pack(side="left", padx=(0, 8))

        win.protocol("WM_DELETE_WINDOW", lambda: choose(default_choice))
        if timeout_seconds and timeout_seconds > 0:
            win.after(int(timeout_seconds * 1000), lambda: choose(default_choice))

        win.update_idletasks()
        width = win.winfo_width()
        height = win.winfo_height()
        x = (win.winfo_screenwidth() - width) // 2
        y = (win.winfo_screenheight() - height) // 2
        win.geometry(f"+{x}+{y}")
        win.focus_force()
        win.mainloop()

    popup_thread = threading.Thread(target=_do_popup, daemon=True)
    popup_thread.start()

    waited = 0.0
    while not result["done"] and waited < timeout_seconds:
        time.sleep(0.5)
        waited += 0.5

    if not result["done"]:
        logger.warning("⏰ 恢复选择超时 (%d秒未响应)，默认停止", timeout_seconds)
        return default_choice
    return str(result["choice"])


def notify_resume_choice(
    title: str,
    message: str,
    timeout_seconds: int = 300,
) -> str:
    """
    Ask how to handle a recoverable single-account task.

    Returns:
        "resume" = continue saved timing/plan
        "rescan" = ignore saved next-seat plan and scan again
        "abort" = keep current booking but do not take over automation
    """
    logger.info("🔔 ====== 恢复任务选择 ======")
    logger.info("📋 %s", title)
    for line in message.split("\n"):
        if line.strip():
            logger.info("   %s", line.strip())
    logger.info("🔔 =========================")

    _show_win32_toast(title, message)
    choice = _show_tkinter_choice(
        title,
        message,
        choices=[
            ("resume", "继续上次计划"),
            ("rescan", "重新扫描"),
            ("abort", "停止"),
        ],
        default_choice="abort",
        timeout_seconds=timeout_seconds,
    )
    logger.info("恢复任务选择: %s", choice)
    return choice


def notify_option_choice(
    title: str,
    message: str,
    choices: list,
    default_choice: str = "abort",
    timeout_seconds: int = 300,
) -> str:
    """
    Ask the user to choose one option from a prepared list.

    choices: list of (value, label) tuples. The caller should include a cancel
    option when cancellation is allowed.
    """
    logger.info("🔔 ====== 方案选择 ======")
    logger.info("📋 %s", title)
    for line in message.split("\n"):
        if line.strip():
            logger.info("   %s", line.strip())
    logger.info("🔔 ====================")

    _show_win32_toast(title, message)
    choice = _show_tkinter_choice(
        title,
        message,
        choices=choices,
        default_choice=default_choice,
        timeout_seconds=timeout_seconds,
    )
    logger.info("方案选择: %s", choice)
    return choice


def notify_info(title: str, message: str) -> None:
    """
    仅通知，不需要用户确认。
    用于多账号模式的执行结果通知。
    """
    logger.info("📢 ====== 通知 ======")
    logger.info("📋 %s", title)
    for line in message.split("\n"):
        if line.strip():
            logger.info("   %s", line.strip())
    logger.info("📢 ==================")

    _show_win32_toast(title, message)


def build_seat_change_notification(
    current_seat: str,
    current_room: str,
    current_end: str,
    next_seat: str,
    next_room: str,
    next_start: str,
    next_end: str,
    same_room: bool,
) -> tuple:
    """
    构建换座通知的标题和内容。

    Returns:
        (title, message)
    """
    title = "🔔 换座提醒 — 找到下一阶段座位"

    room_note = "同房间" if same_room else f"跨房间: {current_room} → {next_room}"
    message = (
        f"当前座位: {current_seat} [{current_room}]\n"
        f"当前预约结束时间: {current_end}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"下一阶段推荐座位:\n"
        f"  座位号: {next_seat}\n"
        f"  房间: {next_room}\n"
        f"  时间段: {next_start} - {next_end}\n"
        f"  持续: {_calc_duration(next_start, next_end)} 分钟\n"
        f"  ({room_note})\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"点击「是」: 取消当前预约并自动预约新座位\n"
        f"点击「否」: 保持当前座位，不换座\n"
        f"(超时 {_get_timeout()} 秒自动放弃)"
    )
    return title, message


def build_no_seat_notification(
    current_end: str,
    target_end: str,
) -> tuple:
    """构建「未找到座位」的通知内容"""
    title = "⚠️ 换座提醒 — 未找到可用座位"
    message = (
        f"当前预约将于 {current_end} 结束\n"
        f"目标结束时间: {target_end}\n\n"
        f"在 {current_end} 之后没有找到可用的座位。\n"
        f"建议手动寻找座位或提前结束今日学习。"
    )
    return title, message


def _calc_duration(start: str, end: str) -> int:
    """计算时间段长度（分钟）"""
    try:
        s_parts = start.strip().split(":")
        e_parts = end.strip().split(":")
        return (int(e_parts[0]) * 60 + int(e_parts[1])) - (
            int(s_parts[0]) * 60 + int(s_parts[1])
        )
    except Exception:
        return 0


def _get_timeout() -> int:
    """读取配置的超时时间"""
    try:
        import config
        return int(getattr(config, "ALLOC_NOTIFY_TIMEOUT", 300))
    except Exception:
        return 300
