"""分配 Worker — 后台线程执行时间分配任务"""
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from PySide6.QtCore import QObject, Signal

from ui.runtime_state import clear_single_runtime_state, save_single_runtime_state


def _bj_now():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


def _time_to_minutes(t: str) -> int:
    parts = t.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _minutes_to_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


# 学校预约系统开放时间
SCHOOL_OPEN_MINUTES = 6 * 60 + 30   # 06:30
SCHOOL_CLOSE_MINUTES = 22 * 60      # 22:00


def _effective_time_range(day_start: str, day_end: str):
    """计算实际有效的起止时间。
    - 开始时间取 max(当前北京时间, 用户配置开始, 学校开门时间)
    - 结束时间取 min(用户配置结束, 学校关门时间)
    返回 (effective_start, effective_end) 或 (None, None) 表示无有效时间段。
    """
    now = _bj_now()
    now_mins = now.hour * 60 + now.minute
    start_mins = _time_to_minutes(day_start)
    end_mins = _time_to_minutes(day_end)

    effective_start = max(now_mins, start_mins, SCHOOL_OPEN_MINUTES)
    effective_end = min(end_mins, SCHOOL_CLOSE_MINUTES)

    if effective_start >= effective_end:
        return None, None

    return _minutes_to_time(effective_start), _minutes_to_time(effective_end)


class AllocWorker(QObject):
    log_line = Signal(str, str)
    finished = Signal()
    status_changed = Signal(str)
    plan_status_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop_event = None
        self._config = {}
        self._active_driver = None
        self._driver_lock = threading.Lock()
        self._single_runtime_state = None
        self._single_runtime_lock = threading.Lock()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: dict):
        if self.is_running():
            return
        self._config = config
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._stop_event:
            self._stop_event.set()
        with self._driver_lock:
            driver = self._active_driver
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
            self._clear_active_driver(driver)

    def _emit(self, text, color="#e8e8f0"):
        self.log_line.emit(text, color)

    def _set_active_driver(self, driver):
        with self._driver_lock:
            self._active_driver = driver

    def _clear_active_driver(self, driver=None):
        with self._driver_lock:
            if driver is None or self._active_driver is driver:
                self._active_driver = None

    def save_runtime_state(self, reason="manual"):
        """Persist the latest in-memory single-account runtime snapshot."""
        with self._single_runtime_lock:
            if not self._single_runtime_state:
                return False
            state = dict(self._single_runtime_state)
        state["reason"] = reason
        return save_single_runtime_state(state)

    def _runtime_config_snapshot(self):
        cfg = self._config or {}
        keys = (
            "campus",
            "room",
            "day_start",
            "day_end",
            "date",
            "cross_room",
            "cross_room_rooms",
            "preferred_seats",
            "priority_mode",
            "cross_room_min_gain_minutes",
            "api_report_include_intervals",
            "pre_notify",
            "auto_cancel",
            "notify_timeout",
        )
        return {key: cfg.get(key) for key in keys if key in cfg}

    def _slot_to_state(self, slot):
        if not slot:
            return None
        if isinstance(slot, dict):
            return {
                "seat_num": str(slot.get("seat_num", "")),
                "room_name": str(slot.get("room_name", "")),
                "start": str(slot.get("start", slot.get("start_time", ""))),
                "end": str(slot.get("end", slot.get("end_time", ""))),
                "booking_start": str(slot.get("booking_start") or slot.get("start") or slot.get("start_time", "")),
                "booking_end": str(slot.get("booking_end") or slot.get("end") or slot.get("end_time", "")),
            }
        return {
            "seat_num": str(getattr(slot, "seat_num", "")),
            "room_name": str(getattr(slot, "room_name", "")),
            "start": str(getattr(slot, "start", getattr(slot, "start_time", ""))),
            "end": str(getattr(slot, "end", getattr(slot, "end_time", ""))),
            "booking_start": str(self._booking_start(slot)) if hasattr(slot, "start") else str(getattr(slot, "start_time", "")),
            "booking_end": str(self._booking_end(slot)) if hasattr(slot, "end") else str(getattr(slot, "end_time", "")),
        }

    def _booking_to_state(self, booking):
        if not booking:
            return None
        return {
            "seat_num": str(getattr(booking, "seat_num", "")),
            "room_name": str(getattr(booking, "room_name", "")),
            "start_time": str(getattr(booking, "start_time", "")),
            "end_time": str(getattr(booking, "end_time", "")),
            "status": str(getattr(booking, "status", "")),
        }

    def _notify_at_for_booking(self, booking, pre_notify):
        try:
            notify_mins = _time_to_minutes(getattr(booking, "end_time")) - int(pre_notify)
            if notify_mins < 0:
                return ""
            return _minutes_to_time(notify_mins)
        except Exception:
            return ""

    def _set_single_runtime_state(
        self,
        phase,
        current=None,
        pending_next_slot=None,
        notify_at="",
        active=True,
        reason="milestone",
        extra=None,
    ):
        cfg = self._config or {}
        state = {
            "active": bool(active),
            "mode": "single",
            "phase": phase,
            "reason": reason,
            "account": str((cfg.get("accounts") or [[""]])[0][0]),
            "config": self._runtime_config_snapshot(),
            "current_booking": self._booking_to_state(current),
            "pending_next_slot": self._slot_to_state(pending_next_slot),
            "notify_at": notify_at or "",
            "target_range": f"{cfg.get('day_start', '')}-{cfg.get('day_end', '')}",
            "pre_notify": cfg.get("pre_notify", 30),
        }
        if extra:
            state.update(extra)
        with self._single_runtime_lock:
            self._single_runtime_state = state
        save_single_runtime_state(state)
        self.plan_status_changed.emit(dict(state))

    def _clear_single_runtime_state(self):
        with self._single_runtime_lock:
            self._single_runtime_state = None
        clear_single_runtime_state()
        self.plan_status_changed.emit({})

    def _preferred_with_resume_slot(self, preferred_seats, campus, slot_dict):
        if not slot_dict:
            return preferred_seats
        room_name = str(slot_dict.get("room_name", "")).strip()
        seat_num = str(slot_dict.get("seat_num", "")).strip()
        if not room_name or not seat_num:
            return preferred_seats

        merged = dict(preferred_seats or {})
        key = f"{campus}/{room_name}"
        values = [str(item).strip() for item in merged.get(key, []) if str(item).strip()]
        normalized = {item.lstrip("0") or item for item in values}
        if (seat_num.lstrip("0") or seat_num) not in normalized:
            values.insert(0, seat_num)
        merged[key] = values
        return merged

    def _cross_room_candidates(self, cfg, campus, target_room):
        """读取用户勾选的跨房间范围；缺省不预选额外房间。"""
        saved = cfg.get("cross_room_rooms") or {}
        if campus in saved:
            selected = list(saved.get(campus, []))
        else:
            selected = []

        primary_room = cfg.get("room", "")
        if primary_room and primary_room != target_room:
            selected.append(primary_room)

        deduped = []
        for room in selected:
            if room and room != target_room and room not in deduped:
                deduped.append(room)
        return deduped

    def _api_item_to_slot(self, item: dict):
        from types import SimpleNamespace
        return SimpleNamespace(
            seat_num=str(item.get("seat_num")),
            room_name=str(item.get("room_name")),
            start=str(item.get("start")),
            end=str(item.get("end")),
            booking_start=str(item.get("booking_start") or item.get("start")),
            booking_end=str(item.get("booking_end") or item.get("end")),
        )

    def _booking_start(self, slot):
        return getattr(slot, "booking_start", slot.start)

    def _booking_end(self, slot):
        return getattr(slot, "booking_end", slot.end)

    def _expected_room_counts(self, plan: dict) -> dict:
        counts = {}
        for room in plan.get("rooms_scanned", []) or []:
            name = room.get("room")
            count = room.get("layout_seat_count")
            if name and isinstance(count, int) and count > 0:
                counts[name] = count
        return counts

    def _visible_seat_count(self, driver) -> int:
        try:
            from selenium.webdriver.common.by import By
            return len([el for el in driver.find_elements(By.CLASS_NAME, "seat-name") if el.is_displayed()])
        except Exception:
            return 0

    def _wait_room_count(self, driver, room_name, expected_count, timeout=8) -> bool:
        if not expected_count:
            return True
        deadline = _time.monotonic() + timeout
        last_count = -1
        while _time.monotonic() < deadline:
            if self._stop_event and self._stop_event.is_set():
                return False
            last_count = self._visible_seat_count(driver)
            if last_count == expected_count:
                return True
            _time.sleep(0.2)
        self._emit(
            f"  [WARN] 房间校验失败: {room_name} 页面座位数={last_count}, API布局数={expected_count}\n",
            "#ffab40",
        )
        return False

    def _enter_room_checked(self, driver, campus, room_name, account="", expected_count=None) -> bool:
        from logic.navigator import enter_room
        for attempt in range(2):
            if self._stop_event and self._stop_event.is_set():
                return False
            if not enter_room(driver, campus, room_name, account=account):
                continue
            if self._wait_room_count(driver, room_name, expected_count):
                return True
            if attempt == 0:
                self._emit(f"  [WARN] 重新进入 {room_name} 以等待正确座位图\n", "#ffab40")
        return False

    def _emit_api_room_probe(self, client, all_rooms, room_name):
        """输出目标房间的轻量 API 探测结果，便于判断接口字段是否可用。"""
        if not all_rooms:
            self._emit("  API探针: room_stats 未返回房间列表\n", "#ffab40")
            return None

        def pick_name(item):
            return item.get("room") or item.get("name") or item.get("roomName") or ""

        target = next((item for item in all_rooms if pick_name(item) == room_name), None)
        if not target:
            samples = ", ".join(pick_name(item) for item in all_rooms[:6] if pick_name(item))
            self._emit(f"  API探针: 未匹配目标房间「{room_name}」，返回样例: {samples}\n", "#ffab40")
            return None

        room_id = target.get("roomId") or target.get("id")
        free = target.get("free", "?")
        total = target.get("total", "?")
        keys = ", ".join(str(k) for k in target.keys())
        self._emit(f"  API目标房间: {room_name} | roomId={room_id} | free={free}/{total}\n", "#00e676")
        self._emit(f"  API字段: {keys}\n", "#8888aa")

        if not room_id:
            self._emit("  API布局: 缺少 roomId，无法继续测试 layout 接口\n", "#ffab40")
            return None

        try:
            layout_data = client.get_room_layout(room_id)
            layout = layout_data.get("layout", {}) if isinstance(layout_data, dict) else {}
            seat_count = 0
            for item in layout.values():
                if isinstance(item, dict) and item.get("type") != "empty" and (item.get("id") or item.get("seatId")):
                    seat_count += 1
            layout_keys = ", ".join(str(k) for k in layout_data.keys()) if isinstance(layout_data, dict) else ""
            self._emit(f"  API布局: seats={seat_count} | data_keys={layout_keys}\n", "#8888aa")
        except Exception as exc:
            self._emit(f"  API布局测试失败: {exc}\n", "#ffab40")

        return room_id

    # ═══════════════════════════════════════════
    #  主入口
    # ═══════════════════════════════════════════
    def _run(self):
        from core.logger import attach_gui_handler, detach_gui_handler
        attach_gui_handler(lambda msg: self._emit(msg))

        try:
            self.status_changed.emit("running")
            self.plan_status_changed.emit({})
            self._emit("LibSeat Allocator 启动...\n", "#00c8ff")

            cfg = self._config
            accounts = cfg.get("accounts", [])
            mode = cfg.get("mode", "single")

            self._emit(f"模式: {'多账号分时段' if mode == 'multi' else '单账号逐段预约'}\n")
            self._emit(f"目标: {cfg.get('campus','')} / {cfg.get('room','')}\n")
            self._emit(f"时段: {cfg.get('day_start','')} — {cfg.get('day_end','')}\n")
            self._emit(f"账号数: {len(accounts)}\n")
            if mode == "single":
                self._emit(f"提前提醒: {cfg.get('pre_notify',30)} 分钟\n")
                self._emit(f"自动取消: {'是' if cfg.get('auto_cancel',False) else '否'}\n")
            self._emit(f"跨房间: {'是' if cfg.get('cross_room', False) else '否'}\n\n")
            if cfg.get("dry_run", True):
                self._emit("测试模式: 仅 API 抓取空闲座位并生成方案，不执行预约\n\n", "#00e676")

            # 注入配置
            self._inject_config(cfg, accounts, mode)

            driver = None
            try:
                if cfg.get("dry_run", True):
                    self._run_api_dry_run(accounts)
                elif mode == "multi":
                    self._run_multi(accounts)
                else:
                    self._run_single(accounts)
            except Exception as e:
                import traceback
                self._emit(f"\n[ERROR] {e}\n{traceback.format_exc()}\n", "#ff5252")
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
        except Exception as exc:
            import traceback
            self._emit(f"\n[FATAL] {type(exc).__name__}: {exc}\n{traceback.format_exc()}\n", "#ff5252")
        finally:
            try:
                detach_gui_handler()
            except Exception:
                pass
            self.status_changed.emit("done")
            self.finished.emit()

    def _inject_config(self, cfg, accounts, mode):
        import sys, types
        m = types.ModuleType("config")
        m.USERS = {acc: {"password": pwd} for acc, pwd in accounts}
        m.TARGET_CAMPUS = cfg.get("campus", "")
        m.TARGET_ROOM = cfg.get("room", "")
        m.ALLOC_DAY_START = cfg.get("day_start", "09:00")
        m.ALLOC_DAY_END = cfg.get("day_end", "21:00")
        m.ALLOC_MAX_ACCOUNTS = min(len(accounts), 3)
        m.ALLOC_DRY_RUN = cfg.get("dry_run", True)
        m.ALLOC_CROSS_ROOM = cfg.get("cross_room", False)
        m.ALLOC_PRE_NOTIFY_MINUTES = cfg.get("pre_notify", 30)
        m.ALLOC_AUTO_CANCEL = cfg.get("auto_cancel", False)
        m.ALLOC_CROSS_ROOMS = []
        m.ALLOC_ACCOUNT_SLOTS = {}
        m.ALLOC_NOTIFY_TIMEOUT = 300
        m.ALLOCATION_MODE = mode
        m.BROWSER = "edge"; m.DRIVER_PATH = ""; m.WEBDRIVER_CACHE = ""
        m.RECEIVER_EMAIL = cfg.get("receiver_email", "")
        m.SMTP_USER = ""; m.SMTP_PASS = ""
        m.LOG_LEVEL = "INFO"; m.GUI_LOG_LEVEL = "INFO"; m.LOG_DIR = "logs"
        sys.modules["config"] = m

    # ═══════════════════════════════════════════
    #  API 测试模式（不预约）
    # ═══════════════════════════════════════════
    def _run_api_dry_run(self, accounts):
        from logic.auth import Authenticator
        from logic.navigator import enter_room
        from logic.api_planner import (
            build_api_plan,
            build_multi_account_schedule_options,
            build_single_followup_preview,
            format_multi_schedule_options_summary,
            format_plan_summary,
            save_plan_report,
        )
        from core.api_client import APIClient, extract_token
        from core.desktop_notify import notify_option_choice
        from core.driver import get_driver

        if not accounts:
            self._emit("[FAIL] 请至少配置一个账号用于登录获取 API token\n", "#ff5252")
            return

        cfg = self._config
        account, password = accounts[0]
        campus = cfg.get("campus", "")
        room = cfg.get("room", "")
        driver = None

        try:
            self._emit("[API测试 1/4] 登录主账号并获取会话...\n", "#7c5cfc")
            driver = get_driver()
            self._set_active_driver(driver)
            driver.maximize_window()
            _time.sleep(0.5)

            auth = Authenticator(driver)
            if not auth.login(account, password, self._stop_event):
                self._emit("[FAIL] 登录失败，无法继续 API 测试\n", "#ff5252")
                return

            self._emit(f"[API测试 2/4] 进入目标房间 {room} 同步页面会话...\n", "#7c5cfc")
            if not enter_room(driver, campus, room, account=account):
                self._emit("[WARN] 进入目标房间失败，仍尝试从登录态提取 token\n", "#ffab40")

            token = extract_token(driver)
            if not token:
                self._emit("[FAIL] Token 提取失败，无法调用座位 API\n", "#ff5252")
                return

            self._emit("[API测试 3/4] API 全量抓取空闲座位时间段...\n", "#7c5cfc")
            client = APIClient(token, driver=driver)

            def progress(message):
                self._emit(f"  {message}\n", "#8888aa")

            plan = build_api_plan(
                client,
                campus=campus,
                target_room=room,
                day_start=cfg.get("day_start", "09:00"),
                day_end=cfg.get("day_end", "21:00"),
                date=cfg.get("date", ""),
                cross_room=cfg.get("cross_room", False),
                cross_room_rooms=self._cross_room_candidates(cfg, campus, room),
                preferred_seats=cfg.get("preferred_seats", {}),
                priority_mode=cfg.get("priority_mode", "longest_first"),
                accounts_count=len(accounts),
                cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
                include_intervals=True if cfg.get("mode") == "multi" else cfg.get("dry_run_include_intervals", True),
                stop_event=self._stop_event,
                progress=progress,
            )

            self._emit("[API测试 4/4] 生成测试报告...\n", "#7c5cfc")
            if cfg.get("mode") == "multi":
                schedule_options = build_multi_account_schedule_options(
                    plan,
                    max_segments=min(len(accounts), 3),
                    campus=campus,
                    target_room=room,
                    preferred_seats=cfg.get("preferred_seats", {}),
                    priority_mode=cfg.get("priority_mode", "longest_first"),
                    cross_room=cfg.get("cross_room", False),
                    cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
                )
                plan["multi_account_schedule_options"] = schedule_options
                plan["multi_account_schedule"] = schedule_options[0]["schedule"] if schedule_options else {}
                report_path = save_plan_report(plan, prefix="api_multi_dry_run_plan")
                summary = format_multi_schedule_options_summary(plan, schedule_options, dry_run=True)
                summary_success = bool(schedule_options)
                if schedule_options:
                    title, message, choices = self._build_multi_booking_options_notification(plan, schedule_options, accounts)
                    selected_id = notify_option_choice(
                        title + "（测试模式）",
                        message + "\n\n测试模式只记录选择，不会预约。",
                        choices=choices,
                        default_choice="abort",
                        timeout_seconds=cfg.get("notify_timeout", 300),
                    )
                    selected_option = next((item for item in schedule_options if item.get("option_id") == selected_id), None)
                    if selected_option:
                        self._emit(f"测试模式已选择方案: {selected_option.get('title', '')}（未执行预约）\n", "#00e676")
                    else:
                        self._emit("测试模式未选择方案，未执行预约。\n", "#ffab40")
            else:
                report_path = save_plan_report(plan)
                summary = format_plan_summary(plan)
                summary_success = plan.get("success")
                final = (plan.get("selection") or {}).get("final_recommendation")
                if plan.get("success") and final:
                    title, message, choices = self._build_api_booking_options_notification(plan)
                    selected_id = notify_option_choice(
                        title + "（测试模式）",
                        message + "\n\n测试模式只记录选择，不会预约；右侧会显示续约预览。",
                        choices=choices,
                        default_choice="abort",
                        timeout_seconds=cfg.get("notify_timeout", 300),
                    )
                    selected_final = self._option_by_id(plan, selected_id) if selected_id != "abort" else None
                    if selected_final:
                        first_slot = self._api_item_to_slot(selected_final)
                        upcoming_preview = build_single_followup_preview(
                            plan,
                            first_slot.end,
                            cfg.get("day_end", "21:00"),
                            campus=campus,
                            current_room=first_slot.room_name,
                            preferred_seats=cfg.get("preferred_seats", {}),
                            priority_mode=cfg.get("priority_mode", "longest_first"),
                            cross_room=cfg.get("cross_room", False),
                            cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
                            max_segments=2,
                        )
                        notify_at = self._notify_at_for_booking(
                            type("BookingPreview", (), {"end_time": first_slot.end})(),
                            cfg.get("pre_notify", 30),
                        )
                        self.plan_status_changed.emit({
                            "active": True,
                            "mode": "single",
                            "phase": "dry_run_preview",
                            "reason": "dry_run_preview",
                            "account": str(account),
                            "current_booking": {
                                "seat_num": first_slot.seat_num,
                                "room_name": first_slot.room_name,
                                "start_time": first_slot.start,
                                "end_time": first_slot.end,
                                "status": "测试预览",
                            },
                            "pending_next_slot": None,
                            "upcoming_slots": [self._slot_to_state(slot) for slot in upcoming_preview],
                            "notify_at": notify_at,
                            "target_range": f"{cfg.get('day_start', '')}-{cfg.get('day_end', '')}",
                            "pre_notify": cfg.get("pre_notify", 30),
                            "dry_run": True,
                        })
                        self._emit(
                            f"测试模式已选择候选: 座位{first_slot.seat_num} [{first_slot.room_name}] "
                            f"{first_slot.start}-{first_slot.end}（未执行预约）\n",
                            "#00e676",
                        )
                    else:
                        self._emit("测试模式未选择候选，未执行预约。\n", "#ffab40")
            color = "#00e676" if summary_success else "#ff5252"
            self._emit("\n" + summary + "\n", color)
            self._emit(f"报告已保存: {report_path}\n", "#00c8ff")
            self._emit("本次为测试模式，未执行任何预约/取消/换座操作。\n", "#00e676")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                self._clear_active_driver(driver)

    # ═══════════════════════════════════════════
    #  多账号模式
    # ═══════════════════════════════════════════
    def _run_multi(self, accounts):
        from logic.auth import Authenticator
        from logic.navigator import enter_room
        from logic.booker import SeatBooker
        from logic.api_planner import (
            build_api_plan,
            build_multi_account_schedule_options,
            format_multi_schedule_options_summary,
            save_plan_report,
        )
        from core.api_client import APIClient, extract_token
        from core.desktop_notify import notify_option_choice
        from core.driver import get_driver
        from core.notifications import send_email

        cfg = self._config
        campus = cfg.get("campus", "")
        room = cfg.get("room", "")
        start = cfg.get("day_start", "09:00")
        end = cfg.get("day_end", "21:00")
        cross_room = cfg.get("cross_room", False)
        max_acc = min(len(accounts), 3)

        # 校正时间：实际开始时间 = max(当前时间, 配置开始, 6:30)
        eff_start, eff_end = _effective_time_range(start, end)
        if eff_start is None:
            self._emit("[FAIL] 当前时间已超过目标时段或不在系统开放时间内\n", "#ff5252")
            return
        if eff_start != start or eff_end != end:
            self._emit(f"⏰ 时间校正: {start}→{eff_start}, {end}→{eff_end}\n", "#ffab40")
        start, end = eff_start, eff_end

        # [1/4] 登录主账号
        primary_acc, primary_pwd = accounts[0]
        self._emit(f"[1/4] 登录主账号 {primary_acc}...\n", "#7c5cfc")
        driver = get_driver()
        self._set_active_driver(driver)
        driver.maximize_window()
        _time.sleep(0.5)

        auth = Authenticator(driver)
        if not auth.login(primary_acc, primary_pwd, self._stop_event):
            self._emit("[FAIL] 登录失败\n", "#ff5252")
            driver.quit()
            return

        # [2/4] 进入房间
        self._emit(f"[2/4] 进入 {room}...\n", "#7c5cfc")
        if not enter_room(driver, campus, room, account=primary_acc):
            self._emit("[FAIL] 进入房间失败\n", "#ff5252")
            driver.quit()
            return

        token = extract_token(driver)
        if not token:
            self._emit("[FAIL] Token 提取失败，无法使用 API 扫描。为避免逐个点击座位，本次不回退 Selenium 扫描。\n", "#ff5252")
            driver.quit()
            return

        client = APIClient(token, driver=driver)

        def progress(message):
            self._emit(f"  {message}\n", "#8888aa")

        # [3/4] API扫描并生成多账号分段方案
        self._emit("[3/4] API扫描空闲座位并生成多账号分段方案（不点击具体座位）...\n", "#7c5cfc")
        plan = build_api_plan(
            client,
            campus=campus,
            target_room=room,
            day_start=start,
            day_end=end,
            date=cfg.get("date", ""),
            cross_room=cross_room,
            cross_room_rooms=self._cross_room_candidates(cfg, campus, room),
            preferred_seats=cfg.get("preferred_seats", {}),
            priority_mode=cfg.get("priority_mode", "longest_first"),
            accounts_count=max_acc,
            cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
            include_intervals=True,
            stop_event=self._stop_event,
            progress=progress,
        )
        schedule_options = build_multi_account_schedule_options(
            plan,
            max_segments=max_acc,
            campus=campus,
            target_room=room,
            preferred_seats=cfg.get("preferred_seats", {}),
            priority_mode=cfg.get("priority_mode", "longest_first"),
            cross_room=cross_room,
            cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
        )
        plan["multi_account_schedule_options"] = schedule_options
        plan["multi_account_schedule"] = schedule_options[0]["schedule"] if schedule_options else {}
        report_path = save_plan_report(plan, prefix="api_multi_booking_plan")
        self._emit("\n" + format_multi_schedule_options_summary(plan, schedule_options, dry_run=False) + "\n", "#00e676" if schedule_options else "#ff5252")
        self._emit(f"API多账号方案报告: {report_path}\n", "#00c8ff")

        if not schedule_options:
            self._emit("[FAIL] API 未生成可预约分段方案，本次不回退逐座位点击扫描。\n", "#ff5252")
            driver.quit()
            return

        title, message, choices = self._build_multi_booking_options_notification(plan, schedule_options, accounts)
        selected_id = notify_option_choice(
            title,
            message,
            choices=choices,
            default_choice="abort",
            timeout_seconds=cfg.get("notify_timeout", 300),
        )
        if selected_id == "abort":
            self._emit("  用户取消多账号预约，本次任务结束\n", "#ffab40")
            driver.quit()
            return

        selected_option = next((item for item in schedule_options if item.get("option_id") == selected_id), None)
        if not selected_option:
            self._emit("  用户选择的方案无效，本次任务结束\n", "#ffab40")
            driver.quit()
            return

        schedule_data = selected_option.get("schedule", {}) or {}
        plan["selected_multi_account_schedule_option"] = selected_option
        plan["multi_account_schedule"] = schedule_data
        self._emit(f"  已选择: {selected_option.get('title', '方案')}\n", "#00e676")

        schedule_segments = [self._api_item_to_slot(seg) for seg in schedule_data.get("segments", [])]

        # [4/4] 执行预约
        self._emit("[4/4] 执行预约...\n", "#7c5cfc")
        booked, failed = [], []

        for idx, seg in enumerate(schedule_segments):
            if self._stop_event.is_set():
                break
            if idx >= len(accounts):
                self._emit(f"  [SKIP] 第{idx+1}段无可用账号\n", "#ffab40")
                failed.append(seg)
                break

            acc, pwd = accounts[idx]
            if idx > 0:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = get_driver()
                self._set_active_driver(driver)
                driver.maximize_window()
                _time.sleep(0.5)
                auth = Authenticator(driver)
                if not auth.login(acc, pwd, self._stop_event):
                    failed.append(seg)
                    self._emit("  [STOP] 登录失败，停止后续账号预约\n", "#ff5252")
                    break
                if not enter_room(driver, campus, seg.room_name, account=acc):
                    failed.append(seg)
                    self._emit("  [STOP] 进入房间失败，停止后续账号预约\n", "#ff5252")
                    break
            elif seg.room_name != room:
                if not enter_room(driver, campus, seg.room_name, account=acc):
                    failed.append(seg)
                    self._emit("  [STOP] 进入房间失败，停止后续账号预约\n", "#ff5252")
                    break

            booker = SeatBooker(driver, account=acc)
            self._emit(f"  [{acc}] 预约 座位{seg.seat_num} [{seg.room_name}] {seg.start}-{seg.end}...\n")
            if not self._book_seat(booker, seg.seat_num, self._booking_start(seg), self._booking_end(seg)):
                failed.append(seg)
                self._emit(f"    [FAIL]\n", "#ff5252")
                self._emit("  [STOP] 当前分段预约失败，停止后续账号预约\n", "#ff5252")
                break
            else:
                booked.append(seg)
                self._emit(f"    [OK]\n", "#00e676")

        # 汇总
        try:
            driver.quit()
        except Exception:
            pass
        self._clear_active_driver(driver)

        self._emit(f"\n{'='*40}\n")
        self._emit(f"完成: {len(booked)} 成功, {len(failed)} 失败\n", "#00c8ff")

        title = f"LibSeat Allocator: {len(booked)}/{len(schedule_segments)} 段成功"
        content = f"时段: {start} - {end}\n房间: {room}\n\n成功:\n"
        for s in booked:
            content += f"  + 座位{s.seat_num} [{s.room_name}] {s.start}-{s.end}\n"
        if failed:
            content += "\n失败:\n"
            for s in failed:
                content += f"  - 座位{s.seat_num} [{s.room_name}] {s.start}-{s.end}\n"
        try:
            send_email(title, content)
            self._emit("邮件已发送\n", "#8888aa")
        except Exception:
            pass

    # ═══════════════════════════════════════════
    #  单账号模式（完整实现）
    # ═══════════════════════════════════════════
    def _run_single(self, accounts):
        from logic.auth import Authenticator
        from logic.navigator import enter_room
        from logic.booker import SeatBooker
        from logic.booking_manager import BookingManager, BookingInfo
        from logic.api_planner import (
            build_api_plan,
            build_single_followup_preview,
            format_plan_summary,
            save_plan_report,
        )
        from core.api_client import APIClient, extract_token
        from core.driver import get_driver
        from core.notifications import build_success_email, send_email
        from core.desktop_notify import (
            notify_and_confirm,
            notify_option_choice,
            notify_resume_choice,
            build_no_seat_notification,
        )

        cfg = self._config
        account, password = accounts[0]
        campus = cfg.get("campus", "")
        room = cfg.get("room", "")
        day_start = cfg.get("day_start", "09:00")
        day_end = cfg.get("day_end", "21:00")
        cross_room = cfg.get("cross_room", False)
        pre_notify = cfg.get("pre_notify", 30)
        auto_cancel = cfg.get("auto_cancel", False)

        # 校正时间：实际开始时间 = max(当前时间, 配置开始, 6:30)
        eff_start, eff_end = _effective_time_range(day_start, day_end)
        if eff_start is None:
            self._emit("[FAIL] 当前时间已超过目标时段或不在系统开放时间内\n", "#ff5252")
            return
        if eff_start != day_start or eff_end != day_end:
            self._emit(f"⏰ 时间校正: {day_start}→{eff_start}, {day_end}→{eff_end}\n", "#ffab40")
        day_start, day_end = eff_start, eff_end

        # [1] 登录
        self._emit(f"[1] 登录 {account}...\n", "#7c5cfc")
        driver = get_driver()
        self._set_active_driver(driver)
        driver.maximize_window()
        _time.sleep(0.5)

        auth = Authenticator(driver)
        if not auth.login(account, password, self._stop_event):
            self._emit("[FAIL] 登录失败\n", "#ff5252")
            driver.quit()
            return

        if not enter_room(driver, campus, room, account=account):
            self._emit("[FAIL] 进入房间失败\n", "#ff5252")
            driver.quit()
            return

        token = extract_token(driver)
        if not token:
            self._emit("[FAIL] Token 提取失败，无法使用 API 扫描。为避免逐个点击座位，本次不回退 Selenium 扫描。\n", "#ff5252")
            driver.quit()
            return

        client = APIClient(token, driver=driver)

        def progress(message):
            self._emit(f"  {message}\n", "#8888aa")

        booker = SeatBooker(driver, account=account)
        current = None
        resume_force_scan_once = False
        resume_pending_slot = None

        resume_state = cfg.get("resume_single_state") or {}
        if isinstance(resume_state, dict) and resume_state.get("active") and resume_state.get("mode") == "single":
            state_account = str(resume_state.get("account", "")).strip()
            saved_current = resume_state.get("current_booking") or {}
            saved_next = resume_state.get("pending_next_slot") or {}
            if (not state_account or state_account == str(account)) and (saved_current or saved_next):
                self._emit("[恢复] 检测到上次单账号运行状态，登录后查询当前预约...\n", "#00c8ff")
                bm = BookingManager(driver, account=account)
                server_current = None
                if bm.navigate_to_my_bookings():
                    server_current = bm.get_current_booking()
                else:
                    self._emit("  [WARN] 无法进入我的预约页面，暂不恢复旧任务\n", "#ffab40")

                if server_current and server_current.is_active and server_current.end_time:
                    saved_room = str(saved_current.get("room_name", "")).strip()
                    if saved_room and not server_current.room_name:
                        server_current.room_name = saved_room
                    if not server_current.room_name:
                        server_current.room_name = room

                    notify_at = resume_state.get("notify_at") or self._notify_at_for_booking(server_current, pre_notify)
                    saved_current_text = (
                        f"{saved_current.get('room_name') or '未知房间'} / 座位{saved_current.get('seat_num') or '?'} / "
                        f"{saved_current.get('start_time') or '?'}-{saved_current.get('end_time') or '?'}"
                    )
                    server_current_text = (
                        f"{server_current.room_name or '未知房间'} / 座位{server_current.seat_num or '?'} / "
                        f"{server_current.start_time or '?'}-{server_current.end_time or '?'}"
                    )
                    saved_next_text = "无"
                    if saved_next:
                        saved_next_text = (
                            f"{saved_next.get('room_name') or '未知房间'} / 座位{saved_next.get('seat_num') or '?'} / "
                            f"{saved_next.get('start') or '?'}-{saved_next.get('end') or '?'}"
                        )

                    title = "恢复单账号自动换座任务"
                    msg = (
                        "已登录并查询到当前有效预约。\n\n"
                        f"服务器当前预约:\n  {server_current_text}\n\n"
                        f"上次关闭前记录:\n  {saved_current_text}\n\n"
                        f"下一次扫描时间:\n  {notify_at or '按当前预约结束时间重新计算'} "
                        f"(提前 {pre_notify} 分钟)\n\n"
                        f"上次第二段推荐:\n  {saved_next_text}\n\n"
                        "请选择:\n"
                        "继续上次计划: 接管当前预约并继续计时/验证上次推荐\n"
                        "重新扫描: 接管当前预约，但忽略上次第二段推荐\n"
                        "停止: 保留当前预约，不继续自动换座"
                    )
                    choice = notify_resume_choice(title, msg, timeout_seconds=cfg.get("notify_timeout", 300))
                    if choice == "abort":
                        self._emit("  用户选择不接管旧任务，当前预约保持不变。\n", "#ffab40")
                        driver.quit()
                        return

                    current = BookingInfo(
                        seat_num=server_current.seat_num or saved_current.get("seat_num", ""),
                        room_name=server_current.room_name or saved_current.get("room_name", room),
                        start_time=server_current.start_time or saved_current.get("start_time", ""),
                        end_time=server_current.end_time or saved_current.get("end_time", ""),
                        status=server_current.status or "有效",
                    )
                    resume_pending_slot = saved_next if choice == "resume" and saved_next else None
                    resume_force_scan_once = bool(choice == "rescan" or resume_pending_slot)
                    notify_at = notify_at or self._notify_at_for_booking(current, pre_notify)
                    self._set_single_runtime_state(
                        "waiting_next_scan",
                        current=current,
                        notify_at=notify_at,
                        reason="resume_takeover",
                        extra={"resumed_from_saved_state": True},
                    )

                    if not bm.return_to_seat_grid():
                        self._emit(f"  返回座位图失败，尝试进入当前预约房间: {current.room_name}\n", "#ffab40")
                    if current.room_name and not enter_room(driver, campus, current.room_name, account=account):
                        self._emit("  [WARN] 无法进入当前预约房间，后续换座前会再次尝试\n", "#ffab40")
                    self._emit(
                        f"  [OK] 已接管当前预约: 座位{current.seat_num} [{current.room_name}] "
                        f"{current.start_time}-{current.end_time}\n\n",
                        "#00e676",
                    )
                else:
                    self._emit("  未查询到有效预约，按当前配置重新开始第一段预约。\n", "#ffab40")

        if current is None:
            # [2] API 扫描并生成候选方案
            self._emit("[2] API 扫描空闲座位时间段（不点击具体座位）...\n", "#7c5cfc")
            first_plan = build_api_plan(
                client,
                campus=campus,
                target_room=room,
                day_start=day_start,
                day_end=day_end,
                date=cfg.get("date", ""),
                cross_room=cross_room,
                cross_room_rooms=self._cross_room_candidates(cfg, campus, room),
                preferred_seats=cfg.get("preferred_seats", {}),
                priority_mode=cfg.get("priority_mode", "longest_first"),
                accounts_count=len(accounts),
                cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
                include_intervals=cfg.get("api_report_include_intervals", True),
                stop_event=self._stop_event,
                progress=progress,
            )
            report_path = save_plan_report(first_plan, prefix="api_booking_plan")
            self._emit("\n" + format_plan_summary(first_plan, dry_run=False) + "\n", "#00e676" if first_plan.get("success") else "#ff5252")
            self._emit(f"API方案报告: {report_path}\n", "#00c8ff")

            final = (first_plan.get("selection") or {}).get("final_recommendation")
            if not first_plan.get("success") or not final:
                self._emit("[FAIL] API 未找到可预约方案，本次不回退逐座位点击扫描。\n", "#ff5252")
                driver.quit()
                return

            title, msg, choices = self._build_api_booking_options_notification(first_plan)
            selected_id = notify_option_choice(
                title,
                msg,
                choices=choices,
                default_choice="abort",
                timeout_seconds=cfg.get("notify_timeout", 300),
            )
            if selected_id == "abort":
                self._emit("  用户取消预约，本次任务结束\n", "#ffab40")
                driver.quit()
                return

            selected_final = self._option_by_id(first_plan, selected_id) or final
            first_slot = self._api_item_to_slot(selected_final)
            self._emit(f"  第一阶段: 座位{first_slot.seat_num} [{first_slot.room_name}] {first_slot.start}-{first_slot.end}\n", "#00e676")

            if first_slot.room_name != room:
                self._emit(f"  切换到推荐房间: {first_slot.room_name}\n", "#7c5cfc")
                if not enter_room(driver, campus, first_slot.room_name, account=account):
                    self._emit("[FAIL] 进入推荐房间失败\n", "#ff5252")
                    driver.quit()
                    return

            if not self._book_seat(booker, first_slot.seat_num, self._booking_start(first_slot), self._booking_end(first_slot)):
                self._emit("[FAIL] 第一阶段预约失败\n", "#ff5252")
                driver.quit()
                return

            current = BookingInfo(
                seat_num=first_slot.seat_num,
                room_name=first_slot.room_name,
                start_time=first_slot.start,
                end_time=first_slot.end,
                status="有效",
            )
            self._emit(f"  [OK] 预约成功!\n\n", "#00e676")

            # 发送第一段成功邮件
            try:
                title, content = build_success_email(account, current.room_name, current.seat_num, current.start_time, current.end_time)
                send_email(title, content)
            except Exception:
                pass

            upcoming_preview = build_single_followup_preview(
                first_plan,
                current.end_time,
                day_end,
                campus=campus,
                current_room=current.room_name,
                preferred_seats=cfg.get("preferred_seats", {}),
                priority_mode=cfg.get("priority_mode", "longest_first"),
                cross_room=cross_room,
                cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
                max_segments=2,
            )
        else:
            upcoming_preview = []

        self._set_single_runtime_state(
            "waiting_next_scan",
            current=current,
            notify_at=self._notify_at_for_booking(current, pre_notify),
            reason="single_loop_started",
            extra={"upcoming_slots": [self._slot_to_state(slot) for slot in upcoming_preview]},
        )

        # [3] 持续循环
        loop_num = 1
        while not self._stop_event.is_set():
            loop_num += 1
            current_end_mins = _time_to_minutes(current.end_time)
            day_end_mins = _time_to_minutes(day_end)

            if current_end_mins >= day_end_mins:
                self._emit(f"已覆盖全天目标 {day_start}-{day_end}，结束。\n", "#00e676")
                self._set_single_runtime_state("completed", current=current, active=False, reason="covered_target_range")
                self._clear_single_runtime_state()
                break

            # 计算等待时间
            notify_at_mins = current_end_mins - pre_notify
            notify_at_text = _minutes_to_time(notify_at_mins) if notify_at_mins >= 0 else ""
            self._set_single_runtime_state(
                "waiting_next_scan",
                current=current,
                notify_at=notify_at_text,
                reason="waiting_next_scan",
                extra={"upcoming_slots": [self._slot_to_state(slot) for slot in upcoming_preview]},
            )
            now = _bj_now()
            now_mins = now.hour * 60 + now.minute

            force_scan_now = bool(resume_force_scan_once)
            resume_force_scan_once = False
            wait_minutes = notify_at_mins - now_mins
            if force_scan_now:
                self._emit("恢复模式: 立即重新扫描并验证上次信息...\n", "#ffab40")
            elif wait_minutes > 0:
                notify_h = notify_at_mins // 60
                notify_m = notify_at_mins % 60
                self._emit(f"下一次扫描: {notify_h:02d}:{notify_m:02d} (距结束 {pre_notify} 分钟前)\n", "#8888aa")

                # 分段等待，每秒检查 stop_event
                waited = 0
                target_wait = wait_minutes * 60
                while waited < target_wait:
                    if self._stop_event.is_set():
                        driver.quit()
                        return
                    sleep_chunk = min(1, target_wait - waited)
                    _time.sleep(sleep_chunk)
                    waited += sleep_chunk
            else:
                self._emit(f"提醒时间已过，立即扫描下一阶段...\n", "#ffab40")

            if self._stop_event.is_set():
                break

            # 重新扫描
            self._emit(f"\n[阶段{loop_num}] API 寻找 {current.end_time} 之后的座位...\n", "#7c5cfc")
            scan_preferred_seats = cfg.get("preferred_seats", {})
            scan_priority_mode = cfg.get("priority_mode", "longest_first")
            if resume_pending_slot:
                scan_preferred_seats = self._preferred_with_resume_slot(scan_preferred_seats, campus, resume_pending_slot)
                scan_priority_mode = "prefer_first"
                self._emit(
                    f"  恢复模式: 优先验证上次推荐 座位{resume_pending_slot.get('seat_num')} "
                    f"[{resume_pending_slot.get('room_name')}]\n",
                    "#ffab40",
                )
            next_plan = build_api_plan(
                client,
                campus=campus,
                target_room=current.room_name,
                day_start=current.end_time,
                day_end=day_end,
                date=cfg.get("date", ""),
                cross_room=cross_room,
                cross_room_rooms=self._cross_room_candidates(cfg, campus, current.room_name),
                preferred_seats=scan_preferred_seats,
                priority_mode=scan_priority_mode,
                accounts_count=len(accounts),
                cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
                include_intervals=cfg.get("api_report_include_intervals", True),
                stop_event=self._stop_event,
                progress=progress,
            )
            resume_pending_slot = None
            report_path = save_plan_report(next_plan, prefix="api_booking_plan")
            self._emit("\n" + format_plan_summary(next_plan, dry_run=False) + "\n", "#00e676" if next_plan.get("success") else "#ffab40")
            self._emit(f"API方案报告: {report_path}\n", "#00c8ff")

            next_final = (next_plan.get("selection") or {}).get("final_recommendation")
            if not next_plan.get("success") or not next_final:
                self._emit("[WARN] API 未找到可用座位\n", "#ffab40")
                self._set_single_runtime_state(
                    "no_next_seat",
                    current=current,
                    notify_at=notify_at_text,
                    active=False,
                    reason="api_no_next_seat",
                    extra={"last_report_path": report_path},
                )
                title, msg = build_no_seat_notification(current.end_time, day_end)
                notify_and_confirm(title, msg, timeout_seconds=120)
                self._clear_single_runtime_state()
                break

            recommended_slot = self._api_item_to_slot(next_final)
            recommended_same_room = recommended_slot.room_name == current.room_name
            self._emit(
                f"  推荐: 座位{recommended_slot.seat_num} [{recommended_slot.room_name}] "
                f"{recommended_slot.start}-{recommended_slot.end} "
                f"({'同房间' if recommended_same_room else '跨房间'})\n",
                "#00e676",
            )
            self._set_single_runtime_state(
                "pending_change_confirmation",
                current=current,
                pending_next_slot=recommended_slot,
                notify_at=notify_at_text,
                reason="next_slot_found",
                extra={"last_report_path": report_path},
            )

            # 通知用户
            if auto_cancel:
                confirmed = True
                next_slot = recommended_slot
                self._emit("  自动模式: 无需用户确认\n", "#8888aa")
            else:
                title, msg, choices = self._build_next_seat_options_notification(current, next_plan)
                selected_id = notify_option_choice(
                    title,
                    msg,
                    choices=choices,
                    default_choice="abort",
                    timeout_seconds=cfg.get("notify_timeout", 300),
                )
                confirmed = selected_id != "abort"
                selected_next = self._option_by_id(next_plan, selected_id) if confirmed else None
                next_slot = self._api_item_to_slot(selected_next or next_final)

            if not confirmed:
                self._emit("  用户拒绝换座，结束\n", "#ffab40")
                self._set_single_runtime_state(
                    "user_declined_change",
                    current=current,
                    pending_next_slot=next_slot,
                    active=False,
                    reason="user_declined_change",
                )
                self._clear_single_runtime_state()
                break

            same_room = next_slot.room_name == current.room_name
            self._emit(
                f"  已选择下一段: 座位{next_slot.seat_num} [{next_slot.room_name}] "
                f"{next_slot.start}-{next_slot.end} ({'同房间' if same_room else '跨房间'})\n",
                "#00e676",
            )
            self._set_single_runtime_state(
                "pending_change_confirmation",
                current=current,
                pending_next_slot=next_slot,
                notify_at=notify_at_text,
                reason="next_slot_selected",
                extra={"last_report_path": report_path},
            )

            # 执行换座
            self._emit("  执行换座...\n", "#7c5cfc")
            self._set_single_runtime_state(
                "changing",
                current=current,
                pending_next_slot=next_slot,
                reason="change_confirmed",
            )
            bm = BookingManager(driver, account=account)

            if not bm.navigate_to_my_bookings():
                self._emit("  [FAIL] 无法进入我的预约页面\n", "#ff5252")
                break
            if not bm.cancel_booking():
                self._emit("  [FAIL] 取消预约失败\n", "#ff5252")
                break
            self._set_single_runtime_state(
                "current_cancelled_booking_next",
                current=current,
                pending_next_slot=next_slot,
                reason="current_cancelled",
            )
            if not bm.return_to_seat_grid():
                self._emit("  [FAIL] 返回座位图失败\n", "#ff5252")
                break

            # 跨房间切换
            if next_slot.room_name != current.room_name:
                if not enter_room(driver, campus, next_slot.room_name, account=account):
                    self._emit("  [FAIL] 进入新房间失败\n", "#ff5252")
                    break

            # 预约新座位
            if not self._book_seat(booker, next_slot.seat_num, self._booking_start(next_slot), self._booking_end(next_slot)):
                self._emit("  [FAIL] 新座位预约失败\n", "#ff5252")
                self._set_single_runtime_state(
                    "new_booking_failed_after_cancel",
                    current=current,
                    pending_next_slot=next_slot,
                    reason="new_booking_failed_after_cancel",
                )
                break

            current = BookingInfo(
                seat_num=next_slot.seat_num,
                room_name=next_slot.room_name,
                start_time=next_slot.start,
                end_time=next_slot.end,
                status="有效",
            )
            self._emit(f"  [OK] 换座成功! 座位{current.seat_num} {current.start_time}-{current.end_time}\n\n", "#00e676")
            upcoming_preview = build_single_followup_preview(
                next_plan,
                current.end_time,
                day_end,
                campus=campus,
                current_room=current.room_name,
                preferred_seats=cfg.get("preferred_seats", {}),
                priority_mode=cfg.get("priority_mode", "longest_first"),
                cross_room=cross_room,
                cross_room_min_gain_minutes=cfg.get("cross_room_min_gain_minutes", 0),
                max_segments=2,
            )
            self._set_single_runtime_state(
                "waiting_next_scan",
                current=current,
                notify_at=self._notify_at_for_booking(current, pre_notify),
                reason="change_success",
                extra={"upcoming_slots": [self._slot_to_state(slot) for slot in upcoming_preview]},
            )

            # 发送邮件
            try:
                title, content = build_success_email(account, current.room_name, current.seat_num, current.start_time, current.end_time)
                send_email(title, content)
            except Exception:
                pass

        # 结束
        try:
            driver.quit()
        except Exception:
            pass
        self._clear_active_driver(driver)
        self._emit(f"\n{'='*40}\n单账号模式结束\n", "#00c8ff")

    def _build_api_booking_notification(self, plan: dict) -> tuple:
        """构建 API 推荐后的首次预约确认弹窗。"""
        cfg = plan.get("config", {}) or {}
        selection = plan.get("selection", {}) or {}

        def fmt(item):
            if not item:
                return "无"
            return (
                f"{item.get('room_name')} / 座位{item.get('seat_num')} / "
                f"{item.get('start')}-{item.get('end')} / "
                f"{item.get('duration_minutes')}分钟"
            )

        final = selection.get("final_recommendation")
        title = "座位预约确认 - API 已生成推荐方案"
        message = (
            f"目标: {cfg.get('campus', '')} / {cfg.get('target_room', '')}\n"
            f"有效时段: {cfg.get('effective_range', '')}\n\n"
            f"当前房间规则选择:\n"
            f"  {fmt(selection.get('current_room_choice'))}\n\n"
            f"当前房间最长时段:\n"
            f"  {fmt(selection.get('current_room_best'))}\n\n"
        )
        if cfg.get("cross_room"):
            message += (
                f"跨房间最佳候选:\n"
                f"  {fmt(selection.get('cross_room_best'))}\n\n"
            )
        message += (
            f"最终推荐:\n"
            f"  {fmt(final)}\n\n"
            f"决策说明: {selection.get('decision_note', '')}\n\n"
            "点击「是」: 预约最终推荐座位\n"
            "点击「否」: 不预约并结束本次任务"
        )
        return title, message

    def _plan_selectable_options(self, plan: dict) -> list:
        selection = plan.get("selection", {}) or {}
        options = list(selection.get("selectable_options") or [])
        final = selection.get("final_recommendation")
        if not options and final:
            options = [dict(final, option_id="opt1", title="最终推荐", reason=selection.get("decision_note", ""), is_recommended=True)]

        normalized = []
        for idx, option in enumerate(options, start=1):
            item = dict(option)
            item.setdefault("option_id", f"opt{idx}")
            item.setdefault("title", f"候选{idx}")
            normalized.append(item)
        return normalized

    def _option_by_id(self, plan: dict, option_id: str):
        for option in self._plan_selectable_options(plan):
            if option.get("option_id") == option_id:
                return option
        return None

    def _format_option_line(self, idx: int, item: dict) -> str:
        marker = " [推荐]" if item.get("is_recommended") else ""
        return (
            f"{idx}. {item.get('title', '候选')}{marker}: "
            f"{item.get('room_name')} / 座位{item.get('seat_num')} / "
            f"{item.get('start')}-{item.get('end')} / "
            f"{item.get('duration_minutes', 0)}分钟"
        )

    def _build_api_booking_options_notification(self, plan: dict) -> tuple:
        """构建首次预约候选选择弹窗。"""
        cfg = plan.get("config", {}) or {}
        selection = plan.get("selection", {}) or {}
        options = self._plan_selectable_options(plan)
        title = "座位预约选择 - API 已生成候选方案"
        lines = [
            f"目标: {cfg.get('campus', '')} / {cfg.get('target_room', '')}",
            f"有效时段: {cfg.get('effective_range', '')}",
            f"决策说明: {selection.get('decision_note', '')}",
            "",
            "请选择要预约的座位:",
        ]
        for idx, option in enumerate(options, start=1):
            lines.append(self._format_option_line(idx, option))
            reason = option.get("reason")
            if reason:
                lines.append(f"   说明: {reason}")
        lines.extend(["", "点击对应按钮预约该候选；点击取消则结束本次任务。"])
        choices = [(option.get("option_id"), f"选{idx}") for idx, option in enumerate(options, start=1)]
        choices.append(("abort", "取消"))
        return title, "\n".join(lines), choices

    def _build_next_seat_options_notification(self, current, plan: dict) -> tuple:
        """构建单账号下一段候选选择弹窗。"""
        cfg = plan.get("config", {}) or {}
        options = self._plan_selectable_options(plan)
        title = "换座提醒 - 请选择下一阶段座位"
        lines = [
            f"当前预约: {current.room_name} / 座位{current.seat_num} / {current.start_time}-{current.end_time}",
            f"下一段扫描范围: {cfg.get('effective_range', '')}",
            "",
            "请选择下一阶段座位:",
        ]
        for idx, option in enumerate(options, start=1):
            lines.append(self._format_option_line(idx, option))
            reason = option.get("reason")
            if reason:
                lines.append(f"   说明: {reason}")
        lines.extend([
            "",
            "点击对应按钮: 取消当前预约并预约该候选",
            "点击取消: 保持当前座位，不换座",
        ])
        choices = [(option.get("option_id"), f"选{idx}") for idx, option in enumerate(options, start=1)]
        choices.append(("abort", "取消"))
        return title, "\n".join(lines), choices

    def _build_multi_booking_options_notification(self, plan: dict, schedule_options: list, accounts: list) -> tuple:
        """构建多账号多套方案选择弹窗。"""
        cfg = plan.get("config", {}) or {}
        title = "多账号预约选择 - API 已生成多套方案"
        lines = [
            f"目标: {cfg.get('campus', '')} / {cfg.get('target_room', '')}",
            f"有效时段: {cfg.get('effective_range', '')}",
            f"可用账号数: {len(accounts)}",
            "",
            "请选择一套完整方案:",
        ]

        for idx, option in enumerate(schedule_options, start=1):
            schedule = option.get("schedule", {}) or {}
            lines.append(f"方案{idx}: {option.get('title', '')}")
            lines.append(f"  {option.get('description', '')}")
            note = option.get("note")
            if note:
                lines.append(f"  说明: {note}")
            for seg_idx, seg in enumerate(schedule.get("segments", []) or [], start=1):
                lines.append(
                    f"  账号{seg_idx}: {seg.get('room_name')} / 座位{seg.get('seat_num')} / "
                    f"{seg.get('start')}-{seg.get('end')} / {seg.get('duration_minutes')}分钟"
                )
            gaps = schedule.get("gaps", []) or []
            if gaps:
                gap_text = "、".join(f"{gap.get('start')}-{gap.get('end')}" for gap in gaps)
                lines.append(f"  未覆盖: {gap_text}")
            lines.append("")

        lines.append("点击对应按钮后，程序会按所选方案依次登录账号并预约。")
        choices = [(option.get("option_id"), f"方案{idx}") for idx, option in enumerate(schedule_options, start=1)]
        choices.append(("abort", "取消"))
        return title, "\n".join(lines), choices

    def _build_multi_booking_notification(self, plan: dict, schedule: dict, accounts: list) -> tuple:
        """构建多账号 API 分段预约确认弹窗。"""
        cfg = plan.get("config", {}) or {}
        title = "多账号预约确认 - API 已生成分段方案"
        lines = [
            f"目标: {cfg.get('campus', '')} / {cfg.get('target_room', '')}",
            f"有效时段: {cfg.get('effective_range', '')}",
            f"账号数: {len(accounts)}",
            f"分段数: {schedule.get('segment_count', 0)}",
            f"覆盖: {schedule.get('total_covered_minutes', 0)}/{schedule.get('desired_minutes', 0)} 分钟",
            "",
            "分段方案:",
        ]

        for idx, seg in enumerate(schedule.get("segments", []) or [], start=1):
            account_label = f"账号{idx}"
            if idx <= len(accounts):
                account_label = f"账号{idx}"
            lines.append(
                f"  {account_label}: {seg.get('room_name')} / 座位{seg.get('seat_num')} / "
                f"{seg.get('start')}-{seg.get('end')} / {seg.get('duration_minutes')}分钟"
            )

        gaps = schedule.get("gaps", []) or []
        if gaps:
            lines.extend(["", "未覆盖时段:"])
            for gap in gaps:
                lines.append(f"  {gap.get('start')}-{gap.get('end')}")

        lines.extend([
            "",
            "点击「是」: 按上述分段依次登录账号并预约",
            "点击「否」: 不预约并结束本次任务",
        ])
        return title, "\n".join(lines)

    # ═══════════════════════════════════════════
    #  工具方法：预约座位（含验证码循环）
    # ═══════════════════════════════════════════
    def _book_seat(self, booker, seat_num, start, end) -> bool:
        """预约单个座位，含验证码重试循环。返回 True/False。"""
        booker.current_seat = str(seat_num)
        booker.current_retry = 0
        if not booker.select_time_and_wait(seat_num, start, end):
            return False
        if not booker.fire_submit_trigger():
            booker.close_popup()
            return False

        for retry in range(1, booker.get_captcha_max_retries() + 1):
            if self._stop_event.is_set():
                return False
            booker.current_retry = retry
            solve_data = booker.pre_solve_captcha()
            if solve_data.get("no_captcha"):
                result = booker.check_result()
                return result.get("status") == "success"
            if not solve_data.get("solved"):
                booker._refresh_click_captcha(previous_key=solve_data.get("captcha_key", ""), wait_timeout=1.0)
                continue
            if booker.fire_captcha_blitz(solve_data):
                result = booker.check_result()
                if result.get("status") == "success":
                    return True
                if result.get("status") in ("stop", "blacklist"):
                    return False
                if result.get("status") == "retry_captcha":
                    booker.last_captcha_auto_refreshed = True
            if booker.last_captcha_auto_refreshed:
                booker.last_captcha_auto_refreshed = False
                continue
            if not booker.is_captcha_popup_present():
                result = booker.check_result()
                if result.get("status") == "success":
                    return True
                if result.get("status") == "retry_captcha":
                    continue
                if result.get("status") in ("stop", "blacklist"):
                    return False
                booker._close_captcha_modal()
                booker.close_popup()
                return False
            booker._refresh_click_captcha(previous_key=solve_data.get("captcha_key", ""), wait_timeout=1.0)
        return False
