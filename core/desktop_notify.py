# core/desktop_notify.py
"""
桌面通知模块

用于单账号模式：在需要换座时弹窗通知用户确认。

支持：
  - tkinter 消息框（Windows/macOS/Linux 原生）
  - 日志记录（无GUI环境回退）
"""

import os
import re
import sys
import threading
import time
import queue
import tempfile
import struct
from core.logger import get_logger

logger = get_logger(__name__)
_ICON_PNG_CACHE = {}


def _app_icon_path() -> str:
    candidates = []
    base_dir = getattr(sys, "_MEIPASS", "")
    if base_dir:
        candidates.append(os.path.join(base_dir, "OIP-C.ico"))
    candidates.extend([
        os.path.abspath("OIP-C.ico"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "OIP-C.ico")),
    ])
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return ""


def _set_window_icon(window) -> None:
    icon = _app_icon_path()
    if not icon:
        return
    try:
        window.iconbitmap(icon)
    except Exception:
        pass


def _popup_palette() -> dict:
    try:
        from ui.theme import C, current_theme

        dark = current_theme() == "dark"
        return {
            "dark": dark,
            "bg": C.BG,
            "panel": C.GRAY_100,
            "header_bg": C.FRAMED_BG,
            "header_border": C.BORDER_ACCENT,
            "input": C.INPUT,
            "input_alt": C.CARD,
            "text": C.TEXT,
            "text_sec": C.TEXT_SEC,
            "text_muted": C.TEXT_MUTED,
            "border": C.BORDER,
            "border_light": C.BORDER_LIGHT,
            "accent": C.ACCENT,
            "accent_hot": C.ACCENT_HOT,
            "accent_soft": C.ACCENT_SOFT,
            "button_secondary": C.INPUT_HOVER,
            "warning_bg": C.WARN_SOFT,
            "warning_fg": C.WARN,
        }
    except Exception:
        return {
            "dark": False,
            "bg": "#ebeaf0",
            "panel": "#f2f6fb",
            "header_bg": "#eaf4ff",
            "header_border": "#b9d9ff",
            "input": "#ffffff",
            "input_alt": "#fbfdff",
            "text": "#172033",
            "text_sec": "#415066",
            "text_muted": "#667085",
            "border": "#c8d7e8",
            "border_light": "#dce7f5",
            "accent": "#2f80ed",
            "accent_hot": "#1f68c7",
            "accent_soft": "#eef5ff",
            "button_secondary": "#ffffff",
            "warning_bg": "#fff8e6",
            "warning_fg": "#7a4a00",
        }


def _icon_png_path(size: int = 96) -> str:
    icon = _app_icon_path()
    if not icon:
        return ""
    try:
        mtime = int(os.path.getmtime(icon))
        key = (icon, size, mtime)
        cached = _ICON_PNG_CACHE.get(key)
        if cached and os.path.exists(cached):
            return cached

        embedded = _extract_png_from_ico(icon, size, mtime)
        if embedded:
            _ICON_PNG_CACHE[key] = embedded
            return embedded

        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QImageReader

        out = os.path.join(tempfile.gettempdir(), f"lnu_libseat_icon_{size}_{mtime}.png")
        if not os.path.exists(out):
            reader = QImageReader(icon)
            reader.setScaledSize(QSize(size, size))
            image = reader.read()
            if image.isNull():
                return ""
            image = image.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not image.save(out, "PNG"):
                return ""
        _ICON_PNG_CACHE[key] = out
        return out
    except Exception as exc:
        logger.debug("Unable to convert app icon for Tk popup: %s", exc)
        return ""


def _extract_png_from_ico(icon: str, size: int, mtime: int) -> str:
    try:
        out = os.path.join(tempfile.gettempdir(), f"lnu_libseat_icon_embedded_{size}_{mtime}.png")
        if os.path.exists(out):
            return out

        with open(icon, "rb") as f:
            data = f.read()
        if len(data) < 6:
            return ""
        reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
        if reserved != 0 or icon_type != 1 or count <= 0:
            return ""

        entries = []
        for index in range(count):
            offset = 6 + index * 16
            if offset + 16 > len(data):
                continue
            width, height, _colors, _reserved, _planes, _bits, bytes_in_res, image_offset = struct.unpack_from(
                "<BBBBHHII",
                data,
                offset,
            )
            width = 256 if width == 0 else width
            height = 256 if height == 0 else height
            image_end = image_offset + bytes_in_res
            if image_offset < len(data) and image_end <= len(data) and data[image_offset:image_offset + 8] == b"\x89PNG\r\n\x1a\n":
                entries.append((abs(width - size), -width * height, image_offset, image_end))
        if not entries:
            return ""
        _distance, _area, image_offset, image_end = sorted(entries)[0]
        with open(out, "wb") as f:
            f.write(data[image_offset:image_end])
        return out
    except Exception as exc:
        logger.debug("Unable to extract PNG frame from app icon: %s", exc)
        return ""


def _fit_photo(photo, size: int):
    try:
        width = max(photo.width(), 1)
        height = max(photo.height(), 1)
        if width > size * 1.25 or height > size * 1.25:
            factor = max(1, min(width // size, height // size))
            if factor > 1:
                return photo.subsample(factor, factor)
        if width < size * 0.75 or height < size * 0.75:
            factor = max(1, round(size / max(width, height)))
            if factor > 1:
                return photo.zoom(factor, factor)
    except Exception:
        pass
    return photo


def _load_icon_photo(master, size: int = 96):
    icon = _app_icon_path()
    if not icon:
        return None
    try:
        import tkinter as tk

        png = _icon_png_path(size)
        if png:
            return _fit_photo(tk.PhotoImage(master=master, file=png), size)
        try:
            from PIL import Image, ImageTk

            image = Image.open(icon)
            image.thumbnail((size, size))
            return ImageTk.PhotoImage(image, master=master)
        except Exception:
            photo = tk.PhotoImage(master=master, file=icon)
            return _fit_photo(photo, size)
    except Exception:
        return None


def _make_popup_header(tk, parent, master, title: str, message: str, palette: dict, width: int = 620):
    frame = tk.Frame(
        parent,
        bg=palette["header_bg"],
        padx=12,
        pady=12,
        highlightbackground=palette["header_border"],
        highlightthickness=1,
    )
    frame.pack(fill="x", pady=(0, 12))

    icon_photo = _load_icon_photo(master, size=96)
    if icon_photo:
        icon_label = tk.Label(frame, image=icon_photo, bg=palette["header_bg"])
        icon_label.image = icon_photo
    else:
        icon_label = tk.Label(
            frame,
            text="💺",
            bg=palette["header_bg"],
            fg=palette["accent"],
            font=("Microsoft YaHei UI", 40),
        )
    icon_label.pack(side="left", padx=(0, 22))

    text_box = tk.Frame(frame, bg=palette["header_bg"])
    text_box.pack(side="left", fill="both", expand=True)
    tk.Label(
        text_box,
        text=title,
        bg=palette["header_bg"],
        fg=palette["text"],
        font=("Microsoft YaHei UI", 11, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Message(
        text_box,
        text=message,
        width=width,
        bg=palette["header_bg"],
        fg=palette["text_sec"],
        font=("Microsoft YaHei UI", 9),
    ).pack(fill="x", pady=(3, 0))
    return frame


def _popup_button(tk, parent, text: str, command, palette: dict, primary: bool = False):
    bg = palette["accent"] if primary else palette["button_secondary"]
    fg = "#ffffff" if primary else palette["text"]
    active_bg = palette["accent_hot"] if primary else palette["accent_soft"]
    return tk.Button(
        parent,
        text=text,
        command=command,
        padx=16,
        pady=7,
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=fg,
        relief="flat",
        borderwidth=0,
        font=("Microsoft YaHei UI", 9, "bold" if primary else "normal"),
        cursor="hand2",
    )


def _item_metrics(item: dict) -> dict:
    return item.get("metrics", {}) or {}


def _selection_filter_options(kind: str):
    if kind == "schedule":
        return ["全部", "完整覆盖", "当前房间", "单账号整段", "跨房间", "有缺口"]
    if kind == "seat":
        return ["全部", "推荐", "当前房间"]
    return ["全部"]


def _selection_sort_options(kind: str):
    if kind == "schedule":
        return ["推荐排序", "时间最长", "缺口最少", "当前房间优先", "账号最少"]
    if kind == "seat":
        return ["推荐排序", "时间最长", "当前房间优先"]
    return ["推荐排序"]


def _filter_item(item: dict, kind: str, mode: str) -> bool:
    if mode == "全部":
        return True
    if kind == "schedule":
        metrics = _item_metrics(item)
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
            target_room = str(item.get("target_room", ""))
            return bool(target_room) and str(item.get("room_name", "")) == target_room
    return True


def _sort_item_key(item: dict, kind: str, mode: str, original_index: int):
    if kind == "schedule":
        metrics = _item_metrics(item)
        covered = int(metrics.get("covered_minutes", 0) or 0)
        gap = int(metrics.get("gap_minutes", 0) or 0)
        segment_count = int(metrics.get("segment_count", 0) or 0)
        current = bool(metrics.get("all_target_room"))
        full = bool(metrics.get("full_cover"))
        if mode == "时间最长":
            return (-covered, gap, 0 if current else 1, segment_count, original_index)
        if mode == "缺口最少":
            return (gap, -covered, 0 if current else 1, segment_count, original_index)
        if mode == "当前房间优先":
            return (0 if current else 1, 0 if full else 1, -covered, gap, segment_count, original_index)
        if mode == "账号最少":
            return (segment_count, 0 if full else 1, -covered, gap, original_index)
    if kind == "seat":
        duration = int(item.get("duration_minutes", 0) or 0)
        current = str(item.get("target_room", "")) and str(item.get("room_name", "")) == str(item.get("target_room", ""))
        recommended = bool(item.get("is_recommended"))
        if mode == "时间最长":
            return (-duration, 0 if recommended else 1, original_index)
        if mode == "当前房间优先":
            return (0 if current else 1, -duration, 0 if recommended else 1, original_index)
    return (original_index,)


def _show_tkinter_selection_list(
    title: str,
    message: str,
    items: list,
    line_builder,
    detail_builder,
    default_choice: str = "abort",
    timeout_seconds: int = 300,
    minsize=(720, 480),
    list_width: int = 100,
    detail_height: int = 10,
    header_width: int = 640,
    kind: str = "generic",
) -> str:
    import tkinter as tk
    from tkinter import ttk

    items = list(items or [])
    indexed_items = list(enumerate(items))
    result = {"choice": default_choice, "done": False}

    def _do_popup():
        palette = _popup_palette()
        root = tk.Tk()
        _set_window_icon(root)
        root.withdraw()

        win = tk.Toplevel(root)
        win.title(title)
        _set_window_icon(win)
        win.attributes("-topmost", True)
        win.minsize(*minsize)
        win.resizable(False, False)
        win.configure(bg=palette["panel"])

        body = tk.Frame(win, padx=18, pady=16, bg=palette["panel"])
        body.pack(fill="both", expand=True)
        _make_popup_header(tk, body, win, title, message, palette=palette, width=header_width)

        control_row = tk.Frame(body, bg=palette["panel"])
        control_row.pack(fill="x", pady=(0, 8))
        filter_var = tk.StringVar(value="全部")
        sort_var = tk.StringVar(value="推荐排序")

        tk.Label(
            control_row,
            text="筛选",
            bg=palette["panel"],
            fg=palette["text_muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(0, 6))
        filter_box = ttk.Combobox(
            control_row,
            textvariable=filter_var,
            values=_selection_filter_options(kind),
            state="readonly",
            width=12,
            font=("Microsoft YaHei UI", 9),
        )
        filter_box.pack(side="left", padx=(0, 12))

        tk.Label(
            control_row,
            text="排序",
            bg=palette["panel"],
            fg=palette["text_muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(0, 6))
        sort_box = ttk.Combobox(
            control_row,
            textvariable=sort_var,
            values=_selection_sort_options(kind),
            state="readonly",
            width=14,
            font=("Microsoft YaHei UI", 9),
        )
        sort_box.pack(side="left", padx=(0, 12))

        count_var = tk.StringVar(value="")
        tk.Label(
            control_row,
            textvariable=count_var,
            bg=palette["panel"],
            fg=palette["text_muted"],
            font=("Microsoft YaHei UI", 9),
            anchor="e",
        ).pack(side="right")

        list_frame = tk.Frame(body, bg=palette["panel"])
        list_frame.pack(fill="both", expand=False, pady=(0, 10))

        listbox = tk.Listbox(
            list_frame,
            height=10,
            width=list_width,
            exportselection=False,
            bg=palette["input"],
            fg=palette["text"],
            selectbackground=palette["accent"],
            selectforeground="#ffffff",
            activestyle="none",
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=palette["border"],
            highlightcolor=palette["accent"],
            font=("Microsoft YaHei UI", 9),
        )
        list_scroll = tk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=list_scroll.set)
        listbox.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")

        detail_frame = tk.Frame(body, bg=palette["panel"])
        detail_frame.pack(fill="both", expand=True, pady=(0, 12))
        detail = tk.Text(
            detail_frame,
            height=detail_height,
            wrap="word",
            bg=palette["input_alt"],
            fg=palette["text"],
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=palette["border"],
            highlightcolor=palette["accent"],
            insertbackground=palette["text"],
            font=("Microsoft YaHei UI", 9),
        )
        detail_scroll = tk.Scrollbar(detail_frame, orient="vertical", command=detail.yview)
        detail.configure(yscrollcommand=detail_scroll.set)
        detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        visible_items = []

        def rebuild_items(_event=None):
            nonlocal visible_items
            filtered = [
                (original_idx, item)
                for original_idx, item in indexed_items
                if _filter_item(item, kind, filter_var.get())
            ]
            filtered.sort(
                key=lambda pair: _sort_item_key(pair[1], kind, sort_var.get(), pair[0])
            )
            visible_items = [item for _idx, item in filtered]
            listbox.delete(0, "end")
            for idx, item in enumerate(visible_items, start=1):
                listbox.insert("end", line_builder(idx, item))
            count_var.set(f"{len(visible_items)}/{len(items)} 项")
            if visible_items:
                listbox.selection_set(0)
                listbox.activate(0)
            refresh_detail()

        def selected_index() -> int:
            selection = listbox.curselection()
            if selection:
                return int(selection[0])
            return 0

        def refresh_detail(_event=None):
            if not visible_items:
                detail.configure(state="normal")
                detail.delete("1.0", "end")
                detail.insert("1.0", "没有符合当前筛选条件的方案。")
                detail.configure(state="disabled")
                return
            idx = selected_index()
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", detail_builder(idx + 1, visible_items[idx]))
            detail.configure(state="disabled")

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

        def confirm():
            if not visible_items:
                choose(default_choice)
                return
            selected = visible_items[selected_index()]
            choose(str(selected.get("option_id") or default_choice))

        button_row = tk.Frame(body, bg=palette["panel"])
        button_row.pack(fill="x")
        _popup_button(tk, button_row, "确定选择", confirm, palette, primary=True).pack(side="left", padx=(0, 8))
        _popup_button(tk, button_row, "取消", lambda: choose(default_choice), palette).pack(side="left")

        listbox.bind("<<ListboxSelect>>", refresh_detail)
        listbox.bind("<Double-Button-1>", lambda _event: confirm())
        filter_box.bind("<<ComboboxSelected>>", rebuild_items)
        sort_box.bind("<<ComboboxSelected>>", rebuild_items)

        def on_list_wheel(event):
            listbox.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def on_detail_wheel(event):
            detail.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        listbox.bind("<MouseWheel>", on_list_wheel)
        detail.bind("<MouseWheel>", on_detail_wheel)
        rebuild_items()

        win.protocol("WM_DELETE_WINDOW", lambda: choose(default_choice))
        if timeout_seconds and timeout_seconds > 0:
            win.after(int(timeout_seconds * 1000), lambda: choose(default_choice))

        win.update_idletasks()
        width = max(int(minsize[0]), win.winfo_width())
        height = max(int(minsize[1]), win.winfo_height())
        x = (win.winfo_screenwidth() - width) // 2
        y = (win.winfo_screenheight() - height) // 2
        win.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        win.focus_force()
        win.mainloop()

    popup_thread = threading.Thread(target=_do_popup, daemon=True)
    popup_thread.start()

    started = time.monotonic()
    while not result["done"]:
        if timeout_seconds and timeout_seconds > 0 and time.monotonic() - started >= timeout_seconds:
            return default_choice
        time.sleep(0.5)
    return str(result["choice"])


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
        _set_window_icon(root)
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
        _set_window_icon(root)
        root.withdraw()

        win = tk.Toplevel(root)
        win.title(title)
        _set_window_icon(win)
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


def _schedule_option_line(index: int, option: dict) -> str:
    metrics = option.get("metrics", {}) or {}
    tags = " ".join(f"[{tag}]" for tag in (option.get("tags") or []))
    return (
        f"方案{index} {tags}  "
        f"覆盖 {metrics.get('covered_minutes', 0)}/{metrics.get('desired_minutes', 0)} 分钟 | "
        f"{metrics.get('segment_count', 0)} 个账号 | "
        f"缺口 {metrics.get('gap_minutes', 0)} 分钟 | "
        f"换房 {metrics.get('room_changes', 0)} 次"
    )


def _schedule_detail_text(index: int, option: dict) -> str:
    schedule = option.get("schedule", {}) or {}
    metrics = option.get("metrics", {}) or {}
    tags = " ".join(f"[{tag}]" for tag in (option.get("tags") or []))
    lines = [
        f"方案{index} {tags}".strip(),
        f"类型: {option.get('title', '')}",
        f"覆盖: {metrics.get('covered_minutes', 0)}/{metrics.get('desired_minutes', 0)} 分钟",
        f"账号: {metrics.get('segment_count', 0)} 个    缺口: {metrics.get('gap_minutes', 0)} 分钟    换房: {metrics.get('room_changes', 0)} 次",
    ]
    note = option.get("note")
    if note:
        lines.append(f"说明: {note}")
    if (
        int(metrics.get("covered_minutes", 0) or 0) < int(metrics.get("desired_minutes", 0) or 0)
        and int(metrics.get("gap_minutes", 0) or 0) == 0
    ):
        lines.append("💡 开始前等待时间未计入缺口，列表仍会按实际覆盖时长排序。")
    pool_count = option.get("candidate_pool_count")
    if pool_count:
        lines.append(f"已生成 {pool_count} 套候选，当前列表为精选方案。")
    lines.append("")
    for seg_idx, seg in enumerate(schedule.get("segments", []) or [], start=1):
        note = seg.get("decision_note")
        line = (
            f"账号{seg_idx}: {seg.get('room_name')} / 座位{seg.get('seat_num')} / "
            f"{seg.get('start')}-{seg.get('end')} / {seg.get('duration_minutes')} 分钟"
        )
        lines.append(line)
        if note:
            lines.append(f"  {note}")
    gaps = schedule.get("gaps", []) or []
    if gaps:
        lines.append("")
        lines.append("未覆盖时段:")
        for gap in gaps:
            lines.append(f"  {gap.get('start')}-{gap.get('end')}")
    return "\n".join(lines)


def _show_tkinter_schedule_list(
    title: str,
    message: str,
    schedule_options: list,
    default_choice: str = "abort",
    timeout_seconds: int = 300,
) -> str:
    import tkinter as tk

    result = {"choice": default_choice, "done": False}

    def _do_popup():
        root = tk.Tk()
        _set_window_icon(root)
        root.withdraw()

        win = tk.Toplevel(root)
        win.title(title)
        _set_window_icon(win)
        win.attributes("-topmost", True)
        win.minsize(760, 520)
        win.configure(bg="#f4f4f4")

        body = tk.Frame(win, padx=18, pady=16, bg="#f4f4f4")
        body.pack(fill="both", expand=True)

        label = tk.Message(
            body,
            text=message,
            width=760,
            bg="#f4f4f4",
            fg="#111111",
            font=("Microsoft YaHei UI", 10),
        )
        label.pack(fill="x", pady=(0, 10))

        listbox = tk.Listbox(
            body,
            height=min(max(len(schedule_options), 3), 8),
            width=110,
            exportselection=False,
            font=("Microsoft YaHei UI", 9),
        )
        listbox.pack(fill="x", pady=(0, 10))

        for idx, option in enumerate(schedule_options, start=1):
            listbox.insert("end", _schedule_option_line(idx, option))

        detail = tk.Text(
            body,
            height=14,
            wrap="word",
            bg="#ffffff",
            fg="#111111",
            relief="solid",
            borderwidth=1,
            font=("Microsoft YaHei UI", 9),
        )
        detail.pack(fill="both", expand=True, pady=(0, 12))

        def selected_index() -> int:
            selection = listbox.curselection()
            if selection:
                return int(selection[0])
            return 0

        def refresh_detail(_event=None):
            if not schedule_options:
                return
            idx = selected_index()
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", _schedule_detail_text(idx + 1, schedule_options[idx]))
            detail.configure(state="disabled")

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

        def confirm():
            if not schedule_options:
                choose(default_choice)
                return
            option = schedule_options[selected_index()]
            choose(str(option.get("option_id") or default_choice))

        button_row = tk.Frame(body, bg="#f4f4f4")
        button_row.pack(fill="x")
        tk.Button(
            button_row,
            text="确认选择",
            command=confirm,
            padx=14,
            pady=6,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            button_row,
            text="取消",
            command=lambda: choose(default_choice),
            padx=14,
            pady=6,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")

        listbox.bind("<<ListboxSelect>>", refresh_detail)
        listbox.bind("<Double-Button-1>", lambda _event: confirm())
        if schedule_options:
            listbox.selection_set(0)
            listbox.activate(0)
            refresh_detail()

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

    started = time.monotonic()
    while not result["done"]:
        if timeout_seconds and timeout_seconds > 0 and time.monotonic() - started >= timeout_seconds:
            logger.warning("方案列表选择超时 (%d秒未响应)，默认取消", timeout_seconds)
            return default_choice
        time.sleep(0.5)
    return str(result["choice"])


def notify_schedule_list_choice(
    title: str,
    message: str,
    schedule_options: list,
    default_choice: str = "abort",
    timeout_seconds: int = 300,
) -> str:
    """Ask the user to choose one complete multi-account schedule from a list."""
    logger.info("🔔 ====== 多账号方案列表选择 ======")
    logger.info("📋 %s", title)
    for line in message.split("\n"):
        if line.strip():
            logger.info("   %s", line.strip())
    for idx, option in enumerate(schedule_options, start=1):
        logger.info("   %s", _schedule_option_line(idx, option))
    logger.info("🔔 ============================")

    _show_win32_toast(title, "请在弹窗中选择一套完整多账号方案")
    choice = _show_tkinter_selection_list(
        title,
        message,
        items=schedule_options,
        line_builder=_schedule_option_line,
        detail_builder=_schedule_detail_text,
        default_choice=default_choice,
        timeout_seconds=timeout_seconds,
        minsize=(980, 700),
        list_width=110,
        detail_height=12,
        header_width=820,
        kind="schedule",
    )
    logger.info("多账号方案列表选择: %s", choice)
    return choice


def _seat_option_line(index: int, option: dict) -> str:
    marker = " ⭐" if option.get("is_recommended") else ""
    return (
        f"候选{index}{marker}  {option.get('title', '候选座位')} | "
        f"{option.get('room_name')} / 座位{option.get('seat_num')} | "
        f"{option.get('start')}-{option.get('end')} | "
        f"{option.get('duration_minutes', 0)} 分钟"
    )


def _seat_detail_text(index: int, option: dict) -> str:
    lines = [
        f"候选{index}" + (" ⭐ 推荐" if option.get("is_recommended") else ""),
        f"📍 房间: {option.get('room_name')}",
        f"💺 座位: {option.get('seat_num')}",
        f"⏱️ 时间: {option.get('start')}-{option.get('end')} ({option.get('duration_minutes', 0)} 分钟)",
    ]
    reason = option.get("reason")
    if reason:
        lines.append(f"🧭 说明: {reason}")
    return "\n".join(lines)


def _show_tkinter_option_list(
    title: str,
    message: str,
    options: list,
    default_choice: str = "abort",
    timeout_seconds: int = 300,
) -> str:
    import tkinter as tk

    result = {"choice": default_choice, "done": False}

    def _do_popup():
        root = tk.Tk()
        _set_window_icon(root)
        root.withdraw()

        win = tk.Toplevel(root)
        win.title(title)
        _set_window_icon(win)
        win.attributes("-topmost", True)
        win.minsize(680, 440)
        win.configure(bg="#f4f4f4")

        body = tk.Frame(win, padx=18, pady=16, bg="#f4f4f4")
        body.pack(fill="both", expand=True)

        label = tk.Message(
            body,
            text=message,
            width=680,
            bg="#f4f4f4",
            fg="#111111",
            font=("Microsoft YaHei UI", 10),
        )
        label.pack(fill="x", pady=(0, 10))

        listbox = tk.Listbox(
            body,
            height=min(max(len(options), 3), 8),
            width=96,
            exportselection=False,
            font=("Microsoft YaHei UI", 9),
        )
        listbox.pack(fill="x", pady=(0, 10))
        for idx, option in enumerate(options, start=1):
            listbox.insert("end", _seat_option_line(idx, option))

        detail = tk.Text(
            body,
            height=8,
            wrap="word",
            bg="#ffffff",
            fg="#111111",
            relief="solid",
            borderwidth=1,
            font=("Microsoft YaHei UI", 9),
        )
        detail.pack(fill="both", expand=True, pady=(0, 12))

        def selected_index() -> int:
            selection = listbox.curselection()
            if selection:
                return int(selection[0])
            return 0

        def refresh_detail(_event=None):
            if not options:
                return
            idx = selected_index()
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", _seat_detail_text(idx + 1, options[idx]))
            detail.configure(state="disabled")

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

        def confirm():
            if not options:
                choose(default_choice)
                return
            choose(str(options[selected_index()].get("option_id") or default_choice))

        buttons = tk.Frame(body, bg="#f4f4f4")
        buttons.pack(fill="x")
        tk.Button(buttons, text="确认选择", command=confirm, padx=14, pady=6, font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="取消", command=lambda: choose(default_choice), padx=14, pady=6, font=("Microsoft YaHei UI", 9)).pack(side="left")

        listbox.bind("<<ListboxSelect>>", refresh_detail)
        listbox.bind("<Double-Button-1>", lambda _event: confirm())
        if options:
            listbox.selection_set(0)
            listbox.activate(0)
            refresh_detail()

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

    started = time.monotonic()
    while not result["done"]:
        if timeout_seconds and timeout_seconds > 0 and time.monotonic() - started >= timeout_seconds:
            logger.warning("候选列表选择超时 (%d秒未响应)，默认取消", timeout_seconds)
            return default_choice
        time.sleep(0.5)
    return str(result["choice"])


def notify_option_list_choice(
    title: str,
    message: str,
    options: list,
    default_choice: str = "abort",
    timeout_seconds: int = 300,
) -> str:
    """Ask the user to choose one seat candidate from a list."""
    logger.info("🔔 ====== 候选座位列表选择 ======")
    logger.info("📋 %s", title)
    for line in message.split("\n"):
        if line.strip():
            logger.info("   %s", line.strip())
    for idx, option in enumerate(options, start=1):
        logger.info("   %s", _seat_option_line(idx, option))
    logger.info("🔔 ===========================")

    _show_win32_toast(title, "请在弹窗中选择一个候选座位")
    choice = _show_tkinter_selection_list(
        title,
        message,
        items=options,
        line_builder=_seat_option_line,
        detail_builder=_seat_detail_text,
        default_choice=default_choice,
        timeout_seconds=timeout_seconds,
        minsize=(860, 620),
        list_width=96,
        detail_height=10,
        header_width=720,
        kind="seat",
    )
    logger.info("候选座位列表选择: %s", choice)
    return choice


class ScanProgressWindow:
    """Small non-blocking Tk progress window for API room/seat scanning."""

    def __init__(self, title: str = "API 扫描进度"):
        self.title = title
        self._queue = queue.Queue()
        self._thread = None
        self._started = False

    def start(self):
        if self._started:
            return self
        self._started = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def update(self, message: str, current: int = None, total: int = None):
        if not self._started:
            self.start()
        self._queue.put(("update", str(message), current, total))

    def close(self):
        if self._started:
            self._queue.put(("close", "", None, None))

    def _extract_total_progress(self, message: str):
        match = re.search(r"\[(\d+)\s*/\s*(\d+)\]\s*API\s*扫描房间\s*(.+)", message)
        if match:
            return int(match.group(1)), int(match.group(2)), match.group(3).strip()
        return None

    def _extract_room_progress(self, message: str):
        match = re.search(r"扫描\s+(.+?):\s*座位\s*(\d+)\s*/\s*(\d+)", message)
        if match:
            return match.group(1).strip(), int(match.group(2)), int(match.group(3))
        return None

    def _extract_room_done(self, message: str):
        match = re.search(r"^(.+?):\s*intervals=", message)
        if match:
            return match.group(1).strip()
        match = re.search(r"^(.+?):\s*没有可用时间段", message)
        if match:
            return match.group(1).strip()
        return ""

    def _run(self):
        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception:
            return

        root = None
        try:
            palette = _popup_palette()
            root = tk.Tk()
            root.title(self.title)
            _set_window_icon(root)
            root.attributes("-topmost", True)
            root.resizable(False, False)
            root.configure(bg=palette["panel"])

            body = tk.Frame(root, padx=18, pady=16, bg=palette["panel"])
            body.pack(fill="both", expand=True)

            title_label = tk.Label(
                body,
                text="🔎 正在扫描 API 空闲座位",
                bg=palette["panel"],
                fg=palette["text"],
                font=("Microsoft YaHei UI", 11, "bold"),
                anchor="w",
            )
            title_label.pack(fill="x", pady=(0, 8))

            warning_label = tk.Message(
                body,
                text="⚠️ 扫描期间请先不要点击其他位置，等待进度窗口自动关闭，避免浏览器焦点或页面状态异常。",
                width=460,
                bg=palette["warning_bg"],
                fg=palette["warning_fg"],
                font=("Microsoft YaHei UI", 9),
                padx=8,
                pady=6,
            )
            warning_label.pack(fill="x", pady=(0, 10))

            message_var = tk.StringVar(value="准备开始扫描...")
            message_label = tk.Label(
                body,
                textvariable=message_var,
                bg=palette["panel"],
                fg=palette["text_sec"],
                font=("Microsoft YaHei UI", 9),
                anchor="w",
                justify="left",
                wraplength=460,
            )
            message_label.pack(fill="x", pady=(0, 10))

            style = ttk.Style(root)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure(
                "LibSeat.Horizontal.TProgressbar",
                background=palette["accent"],
                troughcolor=palette["border_light"],
                bordercolor=palette["border"],
                lightcolor=palette["accent"],
                darkcolor=palette["accent"],
            )
            total_title_var = tk.StringVar(value="总体进度：等待房间列表...")
            tk.Label(
                body,
                textvariable=total_title_var,
                bg=palette["panel"],
                fg=palette["text"],
                font=("Microsoft YaHei UI", 9, "bold"),
                anchor="w",
            ).pack(fill="x", pady=(2, 4))

            total_progress = ttk.Progressbar(
                body,
                orient="horizontal",
                length=460,
                mode="indeterminate",
                style="LibSeat.Horizontal.TProgressbar",
            )
            total_progress.pack(fill="x")
            total_progress.start(12)

            total_percent_var = tk.StringVar(value="")
            tk.Label(
                body,
                textvariable=total_percent_var,
                bg=palette["panel"],
                fg=palette["text_muted"],
                font=("Microsoft YaHei UI", 8),
                anchor="e",
            ).pack(fill="x", pady=(5, 8))

            current_title_var = tk.StringVar(value="当前房间：等待开始...")
            tk.Label(
                body,
                textvariable=current_title_var,
                bg=palette["panel"],
                fg=palette["text"],
                font=("Microsoft YaHei UI", 9, "bold"),
                anchor="w",
            ).pack(fill="x", pady=(0, 4))

            room_progress = ttk.Progressbar(
                body,
                orient="horizontal",
                length=460,
                mode="indeterminate",
                style="LibSeat.Horizontal.TProgressbar",
            )
            room_progress.pack(fill="x")
            room_progress.start(12)

            room_percent_var = tk.StringVar(value="")
            tk.Label(
                body,
                textvariable=room_percent_var,
                bg=palette["panel"],
                fg=palette["text_muted"],
                font=("Microsoft YaHei UI", 8),
                anchor="e",
            ).pack(fill="x", pady=(5, 0))

            total_state = {"index": 0, "total": 0, "room": "", "determinate": False}
            room_state = {"current": None, "total": None, "room": "", "determinate": False}

            def update_total_bar(value=None):
                total = int(total_state.get("total") or 0)
                if not total:
                    if not total_state["determinate"]:
                        total_progress.configure(mode="indeterminate")
                        total_progress.start(12)
                    return
                total_progress.stop()
                total_progress.configure(mode="determinate", maximum=max(total, 1), value=max(0, min(value if value is not None else total_state["index"] - 1, total)))
                total_state["determinate"] = True

            def poll():
                try:
                    while True:
                        kind, message, current, total = self._queue.get_nowait()
                        if kind == "close":
                            try:
                                root.destroy()
                            except Exception:
                                pass
                            return
                        if kind == "update":
                            message_var.set(message)
                            total_info = self._extract_total_progress(message)
                            if total_info:
                                room_index, room_total, room_name = total_info
                                total_state.update({"index": room_index, "total": room_total, "room": room_name})
                                total_title_var.set(f"总体进度：扫描 {room_name} ({room_index}/{room_total})")
                                total_percent_var.set(f"已完成 {max(0, room_index - 1)}/{room_total} 个房间")
                                update_total_bar(max(0, room_index - 1))
                                current_title_var.set(f"当前房间：{room_name}")
                                room_state.update({"current": None, "total": None, "room": room_name, "determinate": False})
                                room_progress.stop()
                                room_progress.configure(mode="indeterminate")
                                room_progress.start(12)
                                room_percent_var.set("读取座位布局...")

                            room_info = self._extract_room_progress(message)
                            if current is not None and total is not None:
                                room_info = (total_state.get("room") or "当前房间", int(current), int(total))
                            if room_info:
                                room_name, seat_current, seat_total = room_info
                                room_state.update({"current": seat_current, "total": seat_total, "room": room_name, "determinate": True})
                                current_title_var.set(f"当前房间：{room_name}")
                                room_progress.stop()
                                room_progress.configure(mode="determinate", maximum=max(seat_total, 1), value=min(seat_current, seat_total))
                                room_percent_var.set(f"{seat_current}/{seat_total} 个座位")
                                if total_state.get("total"):
                                    room_fraction = min(seat_current, seat_total) / max(seat_total, 1)
                                    update_total_bar(max(0, int(total_state.get("index") or 1) - 1) + room_fraction)
                                    total_percent_var.set(
                                        f"房间 {total_state.get('index', 0)}/{total_state.get('total', 0)}，当前房间 {seat_current}/{seat_total}"
                                    )

                            done_room = self._extract_room_done(message)
                            if done_room and total_state.get("total") and done_room == total_state.get("room"):
                                update_total_bar(int(total_state.get("index") or 0))
                                total_percent_var.set(f"已完成 {total_state.get('index', 0)}/{total_state.get('total', 0)} 个房间")
                                if room_state["determinate"]:
                                    room_progress.stop()
                                    room_progress.configure(
                                        mode="determinate",
                                        maximum=max(room_state["total"] or 1, 1),
                                        value=room_state["total"] or 1,
                                    )
                except queue.Empty:
                    pass
                try:
                    root.after(120, poll)
                except Exception:
                    pass

            root.after(120, poll)
            root.update_idletasks()
            width = root.winfo_width()
            height = root.winfo_height()
            x = (root.winfo_screenwidth() - width) // 2
            y = (root.winfo_screenheight() - height) // 2
            root.geometry(f"+{max(0, x)}+{max(0, y)}")
            root.focus_force()
            root.mainloop()
        except Exception as exc:
            logger.debug("Scan progress window failed: %s", exc)
            try:
                if root:
                    root.destroy()
            except Exception:
                pass


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
