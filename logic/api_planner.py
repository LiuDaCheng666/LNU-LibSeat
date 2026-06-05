"""API-only free-seat scanner and dry-run planner.

This module enumerates every available start/end option returned by libseat
and builds a recommendation without touching the booking endpoints.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from core.logger import get_logger


logger = get_logger(__name__)

SCHOOL_OPEN_MINUTES = 6 * 60 + 30
SCHOOL_CLOSE_MINUTES = 22 * 60


def bj_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


def bj_date(now: Optional[datetime] = None) -> str:
    return (now or bj_now()).strftime("%Y-%m-%d")


def time_to_minutes(value: str) -> int:
    parts = str(value).strip().split(":")
    if len(parts) < 2:
        raise ValueError(f"invalid time: {value!r}")
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def campus_building_id(campus: str) -> int:
    return 2 if "崇山" in str(campus) else 1


def effective_time_range(
    day_start: str,
    day_end: str,
    date: str = "",
    now: Optional[datetime] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Return the real query window after applying current time and school hours."""
    now = now or bj_now()
    start_mins = time_to_minutes(day_start)
    end_mins = time_to_minutes(day_end)

    if not date or date == bj_date(now):
        start_mins = max(start_mins, now.hour * 60 + now.minute)

    start_mins = max(start_mins, SCHOOL_OPEN_MINUTES)
    end_mins = min(end_mins, SCHOOL_CLOSE_MINUTES)

    if start_mins >= end_mins:
        return None, None
    return minutes_to_time(start_mins), minutes_to_time(end_mins)


def _option_id(option: Any) -> str:
    if isinstance(option, dict):
        return str(option.get("id", "")).strip()
    return str(option).strip()


def _option_text(option: Any) -> str:
    if isinstance(option, dict):
        for key in ("name", "text", "label", "value"):
            value = option.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return str(option).strip()


def _parse_api_time(option: Any, now_mins: int) -> Tuple[Optional[int], str]:
    raw_id = _option_id(option)
    raw_text = _option_text(option)
    probe_values = [raw_id, raw_text]

    for value in probe_values:
        if not value:
            continue
        lowered = value.lower()
        if lowered == "now":
            return now_mins, "now"
        if value.isdigit():
            mins = int(value)
            return mins, minutes_to_time(mins)
        match = re.search(r"(\d{1,2}):(\d{2})", value)
        if match:
            return int(match.group(1)) * 60 + int(match.group(2)), f"{int(match.group(1)):02d}:{match.group(2)}"
    return None, raw_text or raw_id


def _truthy_enabled(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("0", "false", "no", "disabled", "disable"):
        return False
    return True


def _normalize_seat(value: Any) -> str:
    text = str(value).strip()
    if text.isdigit():
        return str(int(text))
    return text.upper()


def _seat_sort_key(value: str):
    text = str(value)
    if text.isdigit():
        return (0, int(text))
    return (1, text)


@dataclass(frozen=True)
class SeatInterval:
    seat_id: str
    seat_num: str
    room_name: str
    start: str
    end: str
    duration_minutes: int
    raw_start: str
    raw_end: str
    status: str = ""
    enabled: bool = True
    source: str = "api"

    def to_dict(self) -> Dict[str, Any]:
        booking_start = "现在" if str(self.raw_start).lower() == "now" else self.start
        return {
            "seat_id": self.seat_id,
            "seat_num": self.seat_num,
            "room_name": self.room_name,
            "start": self.start,
            "end": self.end,
            "booking_start": booking_start,
            "booking_end": self.end,
            "duration_minutes": self.duration_minutes,
            "raw_start": self.raw_start,
            "raw_end": self.raw_end,
            "status": self.status,
            "enabled": self.enabled,
            "source": self.source,
        }


@dataclass
class RoomScan:
    room_name: str
    room_id: int
    layout_seat_count: int
    intervals: List[SeatInterval]
    errors: Counter

    def best_per_seat(self) -> List[SeatInterval]:
        best: Dict[str, SeatInterval] = {}
        for interval in sorted(self.intervals, key=_interval_rank):
            if interval.seat_id not in best:
                best[interval.seat_id] = interval
        return sorted(best.values(), key=_interval_rank)

    def top_interval(self) -> Optional[SeatInterval]:
        best = self.best_per_seat()
        return best[0] if best else None

    def to_dict(self, include_intervals: bool = True) -> Dict[str, Any]:
        best = self.best_per_seat()
        result = {
            "room": self.room_name,
            "roomId": self.room_id,
            "layout_seat_count": self.layout_seat_count,
            "interval_count": len(self.intervals),
            "best_per_seat_count": len(best),
            "top": best[0].to_dict() if best else None,
            "top20": [item.to_dict() for item in best[:20]],
            "errors": dict(self.errors.most_common(10)),
        }
        if include_intervals:
            result["intervals"] = [item.to_dict() for item in sorted(self.intervals, key=_interval_rank)]
        return result


def _interval_rank(interval: SeatInterval):
    return (
        -interval.duration_minutes,
        time_to_minutes(interval.start),
        time_to_minutes(interval.end),
        interval.room_name,
        _seat_sort_key(interval.seat_num),
    )


def _room_name(room_info: Dict[str, Any]) -> str:
    return str(room_info.get("room") or room_info.get("name") or room_info.get("roomName") or "")


def _room_id(room_info: Dict[str, Any]) -> Optional[int]:
    value = room_info.get("roomId") or room_info.get("id")
    if value in (None, ""):
        return None
    return int(value)


def _layout_seats(layout_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    layout = {}
    if isinstance(layout_data, dict):
        layout = layout_data.get("layout") or layout_data

    seats: List[Dict[str, Any]] = []
    for item in layout.values() if isinstance(layout, dict) else []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "empty":
            continue
        seat_id = item.get("id") or item.get("seatId")
        if not seat_id:
            continue

        disabled = item.get("disabled")
        enabled = _truthy_enabled(item.get("enabled", item.get("enable", item.get("isEnable"))), True)
        if _truthy_enabled(disabled, False):
            enabled = False

        seats.append({
            "seat_id": str(seat_id),
            "seat_num": str(
                item.get("name")
                or item.get("seatName")
                or item.get("label")
                or item.get("num")
                or seat_id
            ),
            "status": str(
                item.get("status")
                or item.get("state")
                or item.get("seatStatus")
                or item.get("statusName")
                or ""
            ),
            "enabled": enabled,
        })
    return seats


def _call_api_with_retries(call, attempts: int = 2, delay_seconds: float = 0.4) -> Dict[str, Any]:
    last: Dict[str, Any] = {}
    for attempt in range(attempts):
        last = call() or {}
        if isinstance(last, dict) and last.get("status") == "success":
            return last
        if attempt < attempts - 1:
            time.sleep(delay_seconds * (attempt + 1))
    return last


def _scan_one_seat(
    client,
    seat: Dict[str, Any],
    room_name: str,
    date: str,
    effective_start_mins: int,
    effective_end_mins: int,
    now_mins: int,
) -> Tuple[List[SeatInterval], Counter]:
    intervals: List[SeatInterval] = []
    errors: Counter = Counter()
    seat_id = seat["seat_id"]

    if not seat.get("enabled", True):
        errors["disabled"] += 1
        return intervals, errors

    start_resp = _call_api_with_retries(lambda: client.get_start_times(int(seat_id), date))
    if start_resp.get("status") != "success":
        errors[f"start:{str(start_resp.get('message', 'error'))[:40]}"] += 1
        return intervals, errors

    start_options = (start_resp.get("data") or {}).get("startTimes") or []
    if not start_options:
        errors["no_start_times"] += 1
        return intervals, errors

    seen = set()
    for start_option in start_options:
        start_param = _option_id(start_option)
        raw_start_mins, raw_start = _parse_api_time(start_option, now_mins)
        if raw_start_mins is None or not start_param:
            errors["bad_start_time"] += 1
            continue

        if raw_start_mins < effective_start_mins or raw_start_mins >= effective_end_mins:
            continue

        end_resp = _call_api_with_retries(lambda: client.get_end_times(int(seat_id), date, start_param))
        if end_resp.get("status") != "success":
            errors[f"end:{str(end_resp.get('message', 'error'))[:40]}"] += 1
            continue

        end_options = (end_resp.get("data") or {}).get("endTimes") or []
        if not end_options:
            errors["no_end_times"] += 1
            continue

        for end_option in end_options:
            raw_end_mins, raw_end = _parse_api_time(end_option, now_mins)
            if raw_end_mins is None:
                errors["bad_end_time"] += 1
                continue
            if raw_end_mins <= raw_start_mins:
                continue

            start_mins = raw_start_mins
            end_mins = min(raw_end_mins, effective_end_mins)
            if end_mins <= start_mins:
                continue

            key = (seat_id, start_mins, end_mins)
            if key in seen:
                continue
            seen.add(key)

            intervals.append(SeatInterval(
                seat_id=seat_id,
                seat_num=seat["seat_num"],
                room_name=room_name,
                start=minutes_to_time(start_mins),
                end=minutes_to_time(end_mins),
                duration_minutes=end_mins - start_mins,
                raw_start=raw_start,
                raw_end=raw_end,
                status=seat.get("status", ""),
                enabled=seat.get("enabled", True),
            ))

    return intervals, errors


def scan_room_intervals(
    client,
    room_id: int,
    room_name: str,
    date: str,
    effective_start: str,
    effective_end: str,
    max_workers: int = 10,
    stop_event=None,
    progress: Optional[Callable[[str], None]] = None,
) -> RoomScan:
    """Scan one room and enumerate every clipped free interval returned by API."""
    progress = progress or (lambda _msg: None)
    layout_data = {}
    seats: List[Dict[str, Any]] = []
    for attempt in range(2):
        layout_data = client.get_room_layout(room_id, date)
        seats = _layout_seats(layout_data)
        if seats:
            break
        if attempt == 0:
            progress(f"{room_name}: layout 为空或超时，重试一次")
            time.sleep(0.5)
    if not seats:
        logger.warning("[API] Room %s returned no seats from layout", room_name)
        return RoomScan(room_name, room_id, 0, [], Counter({"no_layout_seats": 1}))

    now = bj_now()
    now_mins = now.hour * 60 + now.minute
    effective_start_mins = time_to_minutes(effective_start)
    effective_end_mins = time_to_minutes(effective_end)
    intervals: List[SeatInterval] = []
    errors: Counter = Counter()

    progress(f"扫描 {room_name}: layout={len(seats)} seats")

    def run_one(seat):
        if stop_event is not None and stop_event.is_set():
            return [], Counter({"stopped": 1})
        try:
            return _scan_one_seat(
                client,
                seat,
                room_name,
                date,
                effective_start_mins,
                effective_end_mins,
                now_mins,
            )
        except Exception as exc:
            return [], Counter({f"exception:{type(exc).__name__}": 1})

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    futures = {executor.submit(run_one, seat) for seat in seats}
    pending = set(futures)
    stopped = False
    try:
        while pending:
            if stop_event is not None and stop_event.is_set():
                stopped = True
                errors["stopped"] += len(pending)
                for future in pending:
                    future.cancel()
                break
            done, pending = concurrent.futures.wait(
                pending,
                timeout=0.2,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                seat_intervals, seat_errors = future.result()
                intervals.extend(seat_intervals)
                errors.update(seat_errors)
    finally:
        executor.shutdown(wait=not stopped, cancel_futures=stopped)

    scan = RoomScan(
        room_name=room_name,
        room_id=room_id,
        layout_seat_count=len(seats),
        intervals=sorted(intervals, key=_interval_rank),
        errors=errors,
    )
    top = scan.top_interval()
    if top:
        progress(
            f"{room_name}: intervals={len(scan.intervals)}, seats={len(scan.best_per_seat())}, "
            f"top={top.seat_num} {top.start}-{top.end} ({top.duration_minutes}min)"
        )
    else:
        progress(f"{room_name}: 没有可用时间段")
    return scan


def _preferred_for_room(preferred_seats: Any, campus: str, room_name: str) -> List[str]:
    if isinstance(preferred_seats, dict):
        values = preferred_seats.get(f"{campus}/{room_name}", [])
    elif isinstance(preferred_seats, list):
        values = preferred_seats
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip() and str(item).strip() != "000"]


def choose_room_interval(
    scan: Optional[RoomScan],
    preferred_seats: Iterable[str] = (),
    priority_mode: str = "longest_first",
) -> Tuple[Optional[SeatInterval], str]:
    if not scan:
        return None, "房间未扫描"
    candidates = scan.best_per_seat()
    if not candidates:
        return None, "房间没有可用时间段"

    preferred = {_normalize_seat(item) for item in preferred_seats}
    if priority_mode == "prefer_first" and preferred:
        preferred_candidates = [
            item for item in candidates
            if _normalize_seat(item.seat_num) in preferred or _normalize_seat(item.seat_id) in preferred
        ]
        if preferred_candidates:
            return preferred_candidates[0], "优先座位模式：选择优先座位表中最长时段"
        return candidates[0], "优先座位均不可用，回退到当前房间最长时段"

    return candidates[0], "最长时段优先"


def _option_key(item: Optional[Dict[str, Any]]) -> Tuple[str, str, str, str]:
    if not item:
        return ("", "", "", "")
    return (
        str(item.get("room_name", "")),
        str(item.get("seat_num", "")),
        str(item.get("start", "")),
        str(item.get("end", "")),
    )


def _make_selectable_option(
    option_id: str,
    title: str,
    interval: Optional[SeatInterval],
    reason: str = "",
    recommended_key: Tuple[str, str, str, str] = ("", "", "", ""),
) -> Optional[Dict[str, Any]]:
    if not interval:
        return None
    item = interval.to_dict()
    item.update({
        "option_id": option_id,
        "title": title,
        "reason": reason,
        "is_recommended": _option_key(item) == recommended_key,
    })
    return item


def _dedupe_options(options: Iterable[Optional[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for option in options:
        if not option:
            continue
        key = _option_key(option)
        if key in seen:
            continue
        seen.add(key)
        option = dict(option)
        option["option_id"] = f"opt{len(deduped) + 1}"
        deduped.append(option)
    return deduped


def _global_best_interval(scans: Iterable[RoomScan]) -> Optional[SeatInterval]:
    candidates: List[SeatInterval] = []
    for scan in scans:
        candidates.extend(scan.best_per_seat())
    if not candidates:
        return None
    return sorted(candidates, key=_interval_rank)[0]


def build_api_plan(
    client,
    campus: str,
    target_room: str,
    day_start: str,
    day_end: str,
    date: str = "",
    cross_room: bool = False,
    preferred_seats: Optional[Dict[str, List[str]]] = None,
    priority_mode: str = "longest_first",
    accounts_count: int = 1,
    cross_room_min_gain_minutes: int = 0,
    cross_room_rooms: Optional[Iterable[str]] = None,
    include_intervals: bool = True,
    stop_event=None,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Build an API-only dry-run report and recommendation."""
    progress = progress or (lambda _msg: None)
    started = bj_now()
    date = date or bj_date(started)
    effective_start, effective_end = effective_time_range(day_start, day_end, date, started)
    if effective_start is None:
        return {
            "started_at_bj": started.isoformat(),
            "success": False,
            "error": "当前时间已超过目标时段或不在系统开放时间内",
            "rooms_scanned": [],
            "selection": {},
            "finished_at_bj": bj_now().isoformat(),
        }

    building_id = campus_building_id(campus)
    room_stats = client.get_room_stats(building_id, date)
    if not room_stats:
        return {
            "started_at_bj": started.isoformat(),
            "success": False,
            "error": "API 未返回房间列表",
            "rooms_scanned": [],
            "selection": {},
            "finished_at_bj": bj_now().isoformat(),
        }

    target_info = next((item for item in room_stats if _room_name(item) == target_room), None)
    if not target_info:
        samples = ", ".join(_room_name(item) for item in room_stats[:8])
        return {
            "started_at_bj": started.isoformat(),
            "success": False,
            "error": f"未在 API 房间列表中找到目标房间: {target_room}; samples={samples}",
            "rooms_scanned": [],
            "selection": {},
            "finished_at_bj": bj_now().isoformat(),
        }

    target_id = _room_id(target_info)
    if not target_id:
        return {
            "started_at_bj": started.isoformat(),
            "success": False,
            "error": f"目标房间缺少 roomId: {target_room}",
            "rooms_scanned": [],
            "selection": {},
            "finished_at_bj": bj_now().isoformat(),
        }

    rooms_to_scan = [target_info]
    if cross_room:
        selected_cross_rooms = None if cross_room_rooms is None else {str(room) for room in cross_room_rooms}
        rooms_to_scan.extend(
            item for item in room_stats
            if (
                _room_name(item) != target_room
                and _room_id(item)
                and (selected_cross_rooms is None or _room_name(item) in selected_cross_rooms)
            )
        )

    scans: List[RoomScan] = []
    scan_by_room: Dict[str, RoomScan] = {}
    for index, room_info in enumerate(rooms_to_scan, start=1):
        if stop_event is not None and stop_event.is_set():
            break
        room_name = _room_name(room_info)
        room_id = _room_id(room_info)
        if not room_name or not room_id:
            continue
        progress(f"[{index}/{len(rooms_to_scan)}] API 扫描房间 {room_name}")
        scan = scan_room_intervals(
            client,
            room_id,
            room_name,
            date,
            effective_start,
            effective_end,
            stop_event=stop_event,
            progress=progress,
        )
        scans.append(scan)
        scan_by_room[room_name] = scan

    target_scan = scan_by_room.get(target_room)
    target_prefs = _preferred_for_room(preferred_seats or {}, campus, target_room)
    current_choice, current_reason = choose_room_interval(target_scan, target_prefs, priority_mode)
    current_room_best = target_scan.top_interval() if target_scan else None

    cross_choice = None
    cross_reason = ""
    cross_room_options: List[Tuple[SeatInterval, str]] = []
    if cross_room:
        cross_candidates = []
        for scan in scans:
            if scan.room_name == target_room:
                continue
            room_prefs = _preferred_for_room(preferred_seats or {}, campus, scan.room_name)
            candidate, reason = choose_room_interval(scan, room_prefs, priority_mode)
            if candidate:
                cross_candidates.append((candidate, reason))
                cross_room_options.append((candidate, reason))
        if cross_candidates:
            cross_candidates.sort(key=lambda item: _interval_rank(item[0]))
            cross_choice, cross_reason = cross_candidates[0]

    final = current_choice
    needs_confirmation = False
    decision_note = "跨房间未启用，使用当前房间推荐"
    if cross_room:
        if cross_choice and not current_choice:
            final = cross_choice
            needs_confirmation = True
            decision_note = "当前房间无可用方案，跨房间候选需要确认"
        elif cross_choice and current_choice:
            gain = cross_choice.duration_minutes - current_choice.duration_minutes
            if gain > cross_room_min_gain_minutes:
                final = cross_choice
                needs_confirmation = True
                decision_note = f"跨房间候选更长，多 {gain} 分钟，需要弹窗确认"
            else:
                decision_note = "跨房间候选未明显优于当前房间，使用当前房间推荐"
        else:
            decision_note = "跨房间未找到可用候选，使用当前房间推荐"

    recommended_key = _option_key(final.to_dict() if final else None)
    selectable_options = _dedupe_options([
        _make_selectable_option(
            "current_rule",
            "当前房间规则选择",
            current_choice,
            current_reason,
            recommended_key,
        ),
        _make_selectable_option(
            "current_best",
            "当前房间最长时段",
            current_room_best,
            "当前房间内持续时间最长",
            recommended_key,
        ),
        _make_selectable_option(
            "global_best",
            "全局最佳时长座位",
            _global_best_interval(scans),
            "所有已扫描房间中持续时间最长",
            recommended_key,
        ),
        *[
            _make_selectable_option(
                f"room_{index}",
                f"{candidate.room_name} 最佳座位",
                candidate,
                reason,
                recommended_key,
            )
            for index, (candidate, reason) in enumerate(cross_room_options, start=1)
        ],
    ])

    plan = {
        "started_at_bj": started.isoformat(),
        "config": {
            "campus": campus,
            "target_room": target_room,
            "date": date,
            "configured_range": f"{day_start}-{day_end}",
            "now_bj": started.strftime("%Y-%m-%d %H:%M"),
            "effective_range": f"{effective_start}-{effective_end}",
            "cross_room": bool(cross_room),
            "cross_room_rooms": list(cross_room_rooms) if cross_room_rooms is not None else None,
            "priority_mode": priority_mode,
            "preferred_seats": target_prefs,
            "accounts_count": accounts_count,
            "cross_room_min_gain_minutes": cross_room_min_gain_minutes,
        },
        "rooms_scanned": [scan.to_dict(include_intervals=include_intervals) for scan in scans],
        "selection": {
            "current_room_choice": current_choice.to_dict() if current_choice else None,
            "current_room_reason": current_reason,
            "current_room_best": current_room_best.to_dict() if current_room_best else None,
            "cross_room_best": cross_choice.to_dict() if cross_choice else None,
            "cross_room_reason": cross_reason,
            "final_recommendation": final.to_dict() if final else None,
            "selectable_options": selectable_options,
            "needs_confirmation": needs_confirmation,
            "decision_note": decision_note,
        },
        "success": final is not None,
        "finished_at_bj": bj_now().isoformat(),
    }
    return plan


def _interval_dict_rank(item: Dict[str, Any]):
    return (
        -int(item.get("duration_minutes", 0)),
        time_to_minutes(item.get("start", "00:00")),
        time_to_minutes(item.get("end", "00:00")),
        str(item.get("room_name", "")),
        _seat_sort_key(str(item.get("seat_num", ""))),
    )


def _candidate_copy(item: Dict[str, Any], end_limit_mins: int) -> Optional[Dict[str, Any]]:
    start = str(item.get("start", ""))
    end = str(item.get("end", ""))
    if not start or not end:
        return None
    start_mins = time_to_minutes(start)
    end_mins = min(time_to_minutes(end), end_limit_mins)
    if end_mins <= start_mins:
        return None
    copied = dict(item)
    copied["end"] = minutes_to_time(end_mins)
    copied["duration_minutes"] = end_mins - start_mins
    copied["booking_start"] = "现在" if str(copied.get("raw_start", "")).lower() == "now" else copied["start"]
    copied["booking_end"] = copied["end"]
    return copied


def _candidate_pool_for_cursor(
    intervals: List[Dict[str, Any]],
    cursor_mins: int,
    end_limit_mins: int,
    tolerance_minutes: int = 30,
) -> List[Dict[str, Any]]:
    pool = []
    max_start = cursor_mins + tolerance_minutes
    for item in intervals:
        start = item.get("start")
        end = item.get("end")
        if not start or not end:
            continue
        start_mins = time_to_minutes(start)
        if start_mins < cursor_mins or start_mins > max_start:
            continue
        if time_to_minutes(end) <= start_mins:
            continue
        copied = _candidate_copy(item, end_limit_mins)
        if copied:
            pool.append(copied)
    return sorted(pool, key=_interval_dict_rank)


def _matches_preferred(item: Dict[str, Any], preferred: Iterable[str]) -> bool:
    pref_set = {_normalize_seat(value) for value in preferred}
    if not pref_set:
        return False
    return (
        _normalize_seat(item.get("seat_num", "")) in pref_set
        or _normalize_seat(item.get("seat_id", "")) in pref_set
    )


def _pick_from_pool(
    pool: List[Dict[str, Any]],
    campus: str,
    target_room: str,
    preferred_seats: Optional[Dict[str, List[str]]],
    priority_mode: str,
    cross_room: bool,
    cross_room_min_gain_minutes: int,
) -> Tuple[Optional[Dict[str, Any]], str]:
    if not pool:
        return None, "没有候选时间段"

    def best(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return sorted(items, key=_interval_dict_rank)[0] if items else None

    def best_with_preferred(items: List[Dict[str, Any]], room_name: str) -> Optional[Dict[str, Any]]:
        if priority_mode == "prefer_first":
            prefs = _preferred_for_room(preferred_seats or {}, campus, room_name)
            preferred_items = [item for item in items if _matches_preferred(item, prefs)]
            if preferred_items:
                return best(preferred_items)
        return best(items)

    current_pool = [item for item in pool if item.get("room_name") == target_room]
    current_best = best_with_preferred(current_pool, target_room)

    if not cross_room:
        return current_best, "跨房间未启用，选择当前房间候选" if current_best else "当前房间无候选"

    cross_best = None
    for room_name in sorted({str(item.get("room_name", "")) for item in pool if item.get("room_name") != target_room}):
        room_items = [item for item in pool if item.get("room_name") == room_name]
        candidate = best_with_preferred(room_items, room_name)
        if candidate and (not cross_best or _interval_dict_rank(candidate) < _interval_dict_rank(cross_best)):
            cross_best = candidate

    if cross_best and not current_best:
        return cross_best, "当前房间无候选，选择跨房间候选"
    if cross_best and current_best:
        gain = int(cross_best.get("duration_minutes", 0)) - int(current_best.get("duration_minutes", 0))
        if gain > cross_room_min_gain_minutes:
            return cross_best, f"跨房间候选更长，多 {gain} 分钟"
    return current_best, "优先当前房间候选" if current_best else "没有可用候选"


def build_multi_account_schedule(
    plan: Dict[str, Any],
    max_segments: int,
    campus: str,
    target_room: str,
    preferred_seats: Optional[Dict[str, List[str]]] = None,
    priority_mode: str = "longest_first",
    cross_room: bool = False,
    cross_room_min_gain_minutes: int = 0,
    tolerance_minutes: int = 30,
    excluded_keys: Optional[Iterable[Tuple[str, str, str, str]]] = None,
) -> Dict[str, Any]:
    """Build a multi-account segmented schedule from a full API scan plan."""
    config = plan.get("config", {}) or {}
    effective_range = str(config.get("effective_range", ""))
    if "-" not in effective_range:
        return {"segments": [], "gaps": [], "total_covered_minutes": 0, "success": False}

    day_start, day_end = effective_range.split("-", 1)
    day_start_mins = time_to_minutes(day_start)
    day_end_mins = time_to_minutes(day_end)
    excluded = {
        (str(room), str(seat), str(start), str(end))
        for room, seat, start, end in (excluded_keys or [])
    }
    intervals: List[Dict[str, Any]] = []
    for room in plan.get("rooms_scanned", []) or []:
        for item in room.get("intervals", []) or []:
            copied = _candidate_copy(item, day_end_mins)
            if copied:
                key = (
                    str(copied.get("room_name", "")),
                    str(copied.get("seat_num", "")),
                    str(copied.get("start", "")),
                    str(copied.get("end", "")),
                )
                if key in excluded:
                    continue
                intervals.append(copied)

    if not intervals:
        return {
            "segments": [],
            "gaps": [{"start": day_start, "end": day_end}],
            "total_covered_minutes": 0,
            "success": False,
        }

    cursor = day_start_mins
    segments: List[Dict[str, Any]] = []
    gaps: List[Dict[str, str]] = []

    for _idx in range(max(0, max_segments)):
        if cursor >= day_end_mins:
            break

        pool = _candidate_pool_for_cursor(intervals, cursor, day_end_mins, tolerance_minutes)
        if not pool:
            future_starts = sorted(
                time_to_minutes(item.get("start", "00:00"))
                for item in intervals
                if item.get("start") and cursor < time_to_minutes(item.get("start")) < day_end_mins
            )
            if not future_starts:
                gaps.append({"start": minutes_to_time(cursor), "end": minutes_to_time(day_end_mins)})
                break
            next_start = future_starts[0]
            if next_start > cursor:
                gaps.append({"start": minutes_to_time(cursor), "end": minutes_to_time(next_start)})
            cursor = next_start
            pool = _candidate_pool_for_cursor(intervals, cursor, day_end_mins, tolerance_minutes)

        chosen, reason = _pick_from_pool(
            pool,
            campus=campus,
            target_room=target_room,
            preferred_seats=preferred_seats,
            priority_mode=priority_mode,
            cross_room=cross_room,
            cross_room_min_gain_minutes=cross_room_min_gain_minutes,
        )
        if not chosen:
            gaps.append({"start": minutes_to_time(cursor), "end": minutes_to_time(day_end_mins)})
            break

        segment = {
            "seat_id": str(chosen.get("seat_id", "")),
            "seat_num": str(chosen.get("seat_num", "")),
            "room_name": str(chosen.get("room_name", "")),
            "start": str(chosen.get("start", "")),
            "end": str(chosen.get("end", "")),
            "booking_start": str(chosen.get("booking_start") or chosen.get("start", "")),
            "booking_end": str(chosen.get("booking_end") or chosen.get("end", "")),
            "raw_start": str(chosen.get("raw_start", "")),
            "raw_end": str(chosen.get("raw_end", "")),
            "duration_minutes": int(chosen.get("duration_minutes", 0)),
            "decision_note": reason,
            "source": "api",
        }
        if not segment["start"] or not segment["end"] or segment["duration_minutes"] <= 0:
            break
        segments.append(segment)
        cursor = time_to_minutes(segment["end"])

    total_covered = sum(int(item.get("duration_minutes", 0)) for item in segments)
    return {
        "segments": segments,
        "gaps": gaps,
        "total_covered_minutes": total_covered,
        "desired_minutes": day_end_mins - day_start_mins,
        "segment_count": len(segments),
        "success": bool(segments),
    }


def _schedule_signature(schedule: Dict[str, Any]) -> Tuple[Tuple[str, str, str, str], ...]:
    return tuple(
        (
            str(seg.get("room_name", "")),
            str(seg.get("seat_num", "")),
            str(seg.get("start", "")),
            str(seg.get("end", "")),
        )
        for seg in schedule.get("segments", []) or []
    )


def _schedule_description(schedule: Dict[str, Any]) -> str:
    segments = schedule.get("segments", []) or []
    rooms = []
    for seg in segments:
        room = str(seg.get("room_name", ""))
        if room and room not in rooms:
            rooms.append(room)
    return (
        f"覆盖 {schedule.get('total_covered_minutes', 0)}/"
        f"{schedule.get('desired_minutes', 0)} 分钟，"
        f"使用 {len(segments)} 个账号，"
        f"{' / '.join(rooms) if rooms else '无可用房间'}"
    )


def build_multi_account_schedule_options(
    plan: Dict[str, Any],
    max_segments: int,
    campus: str,
    target_room: str,
    preferred_seats: Optional[Dict[str, List[str]]] = None,
    priority_mode: str = "longest_first",
    cross_room: bool = False,
    cross_room_min_gain_minutes: int = 0,
    max_options: int = 3,
) -> List[Dict[str, Any]]:
    """Build several complete multi-account schedules for the user to choose from."""
    candidates: List[Tuple[str, str, Dict[str, Any]]] = []

    one_account = build_multi_account_schedule(
        plan,
        max_segments=1,
        campus=campus,
        target_room=target_room,
        preferred_seats=preferred_seats,
        priority_mode=priority_mode,
        cross_room=cross_room,
        cross_room_min_gain_minutes=cross_room_min_gain_minutes,
    )
    candidates.append(("少账号优先方案", "优先尝试只使用账号1；若一个座位能覆盖目标时长，这就是完整方案。", one_account))

    one_account_signature = set(_schedule_signature(one_account))
    one_account_full = (
        len(one_account.get("segments", []) or []) == 1
        and int(one_account.get("total_covered_minutes", 0)) >= int(one_account.get("desired_minutes", 0))
    )
    if one_account_full and one_account_signature:
        current_room_segmented = build_multi_account_schedule(
            plan,
            max_segments=max_segments,
            campus=campus,
            target_room=target_room,
            preferred_seats=preferred_seats,
            priority_mode=priority_mode,
            cross_room=False,
            cross_room_min_gain_minutes=cross_room_min_gain_minutes,
            excluded_keys=one_account_signature,
        )
        candidates.append(("当前房间分段备选", "避开少账号方案中的整段座位，尝试生成同房间多段方案。", current_room_segmented))

    current_room = build_multi_account_schedule(
        plan,
        max_segments=max_segments,
        campus=campus,
        target_room=target_room,
        preferred_seats=preferred_seats,
        priority_mode=priority_mode,
        cross_room=False,
        cross_room_min_gain_minutes=cross_room_min_gain_minutes,
    )
    candidates.append(("当前房间优先方案", "只使用当前目标房间的座位，宁可覆盖时间短一些。", current_room))

    best_coverage = build_multi_account_schedule(
        plan,
        max_segments=max_segments,
        campus=campus,
        target_room=target_room,
        preferred_seats=preferred_seats,
        priority_mode="longest_first",
        cross_room=cross_room,
        cross_room_min_gain_minutes=cross_room_min_gain_minutes,
    )
    candidates.append(("最长覆盖方案", "允许使用勾选的跨房间范围，优先覆盖更长时间。", best_coverage))

    room_names = [
        str(room.get("room", ""))
        for room in plan.get("rooms_scanned", []) or []
        if room.get("room")
    ]
    for room_name in room_names:
        if room_name == target_room:
            continue
        room_only = build_multi_account_schedule(
            plan,
            max_segments=max_segments,
            campus=campus,
            target_room=room_name,
            preferred_seats=preferred_seats,
            priority_mode=priority_mode,
            cross_room=False,
            cross_room_min_gain_minutes=cross_room_min_gain_minutes,
        )
        candidates.append((f"{room_name} 房间方案", "只使用该勾选房间的最佳分段。", room_only))

    options: List[Dict[str, Any]] = []
    seen = set()
    for title, note, schedule in candidates:
        if not schedule.get("success") or not schedule.get("segments"):
            continue
        signature = _schedule_signature(schedule)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        options.append({
            "option_id": f"schedule{len(options) + 1}",
            "title": title,
            "description": _schedule_description(schedule),
            "note": note,
            "schedule": schedule,
        })
        if len(options) >= max_options:
            break
    return options


def build_single_followup_preview(
    plan: Dict[str, Any],
    current_end: str,
    day_end: str,
    campus: str,
    current_room: str,
    preferred_seats: Optional[Dict[str, List[str]]] = None,
    priority_mode: str = "longest_first",
    cross_room: bool = False,
    cross_room_min_gain_minutes: int = 0,
    max_segments: int = 2,
    tolerance_minutes: int = 30,
) -> List[Dict[str, Any]]:
    """Preview likely next single-account segments from an existing scan report."""
    try:
        cursor = time_to_minutes(current_end)
        day_end_mins = time_to_minutes(day_end)
    except Exception:
        return []

    intervals: List[Dict[str, Any]] = []
    for room in plan.get("rooms_scanned", []) or []:
        for item in room.get("intervals", []) or []:
            copied = _candidate_copy(item, day_end_mins)
            if copied:
                intervals.append(copied)
    if not intervals:
        return []

    segments: List[Dict[str, Any]] = []
    target_room = current_room
    for _idx in range(max(0, max_segments)):
        if cursor >= day_end_mins:
            break
        pool = _candidate_pool_for_cursor(intervals, cursor, day_end_mins, tolerance_minutes)
        if not pool:
            break
        chosen, reason = _pick_from_pool(
            pool,
            campus=campus,
            target_room=target_room,
            preferred_seats=preferred_seats,
            priority_mode=priority_mode,
            cross_room=cross_room,
            cross_room_min_gain_minutes=cross_room_min_gain_minutes,
        )
        if not chosen:
            break
        segment = dict(chosen)
        segment["decision_note"] = reason
        segment["source"] = "preview"
        segments.append(segment)
        cursor = time_to_minutes(str(segment.get("end", "00:00")))
        target_room = str(segment.get("room_name", target_room))
    return segments


def _short_scan_error(key: str) -> str:
    text = str(key or "未知原因").replace("\n", " ").strip()
    text = text.replace("HTTPConnectionPool(host='libseat.lnu.edu.cn', port=80): ", "")
    text = text.replace("Max retries exceeded with url:", "重试后仍失败:")
    if text.startswith("start:"):
        text = "开始时间接口: " + text[len("start:"):]
    elif text.startswith("end:"):
        text = "结束时间接口: " + text[len("end:"):]
    return text[:60]


def _scan_warning_summary(rooms: List[Dict[str, Any]]) -> str:
    warning_prefixes = ("start:", "end:", "exception:")
    warning_keys = {"no_layout_seats", "bad_start_time", "bad_end_time"}
    total = 0
    room_parts: List[str] = []
    for room in rooms or []:
        errors = room.get("errors") or {}
        if not isinstance(errors, dict):
            continue
        notable = []
        for key, value in errors.items():
            key_text = str(key)
            if key_text.startswith(warning_prefixes) or key_text in warning_keys:
                count = int(value or 0)
                if count > 0:
                    notable.append((key_text, count))
        if not notable:
            continue
        room_total = sum(count for _, count in notable)
        total += room_total
        reasons = "，".join(f"{_short_scan_error(key)} x{count}" for key, count in notable[:2])
        room_parts.append(f"{room.get('room', '未知房间')} {room_total} 次（{reasons}）")

    if not total:
        return ""
    detail = "；".join(room_parts[:3])
    suffix = f"：{detail}" if detail else ""
    return f"局部接口警告: {total} 次，已跳过对应座位/时间点，其他成功数据仍用于生成方案{suffix}"


def format_multi_schedule_summary(plan: Dict[str, Any], schedule: Dict[str, Any], dry_run: bool = False) -> str:
    rooms = plan.get("rooms_scanned", []) or []
    total_intervals = sum(int(room.get("interval_count", 0)) for room in rooms)
    config = plan.get("config", {}) or {}
    lines = [
        "API多账号测试完成：只生成分段方案，未执行预约。" if dry_run else "API多账号分段方案生成完成：等待确认后才会执行预约。",
        f"有效时段: {config.get('effective_range', '')}",
        f"扫描房间: {len(rooms)} 个，空闲时间段: {total_intervals} 条",
        f"分段方案: {schedule.get('segment_count', 0)} 段，覆盖 {schedule.get('total_covered_minutes', 0)}/{schedule.get('desired_minutes', 0)} 分钟",
    ]
    warning_summary = _scan_warning_summary(rooms)
    if warning_summary:
        lines.append(warning_summary)
    for idx, seg in enumerate(schedule.get("segments", []) or [], start=1):
        lines.append(
            f"第{idx}段: {seg.get('room_name')} / 座位{seg.get('seat_num')} / "
            f"{seg.get('start')}-{seg.get('end')} / {seg.get('duration_minutes')}分钟"
        )
    for gap in schedule.get("gaps", []) or []:
        lines.append(f"缺口: {gap.get('start')}-{gap.get('end')}")
    return "\n".join(lines)


def format_multi_schedule_options_summary(
    plan: Dict[str, Any],
    schedule_options: List[Dict[str, Any]],
    dry_run: bool = False,
) -> str:
    rooms = plan.get("rooms_scanned", []) or []
    total_intervals = sum(int(room.get("interval_count", 0)) for room in rooms)
    config = plan.get("config", {}) or {}
    lines = [
        "API多账号测试完成：只生成可选方案，未执行预约。" if dry_run else "API多账号分段方案生成完成：等待选择后才会执行预约。",
        f"有效时段: {config.get('effective_range', '')}",
        f"扫描房间: {len(rooms)} 个，空闲时间段: {total_intervals} 条",
        f"可选方案: {len(schedule_options)} 套",
    ]
    warning_summary = _scan_warning_summary(rooms)
    if warning_summary:
        lines.append(warning_summary)
    for idx, option in enumerate(schedule_options, start=1):
        schedule = option.get("schedule", {}) or {}
        lines.append(f"方案{idx}: {option.get('title', '')} - {option.get('description', '')}")
        for seg_idx, seg in enumerate(schedule.get("segments", []) or [], start=1):
            lines.append(
                f"  账号{seg_idx}: {seg.get('room_name')} / 座位{seg.get('seat_num')} / "
                f"{seg.get('start')}-{seg.get('end')} / {seg.get('duration_minutes')}分钟"
            )
        for gap in schedule.get("gaps", []) or []:
            lines.append(f"  缺口: {gap.get('start')}-{gap.get('end')}")
    return "\n".join(lines)


def save_plan_report(plan: Dict[str, Any], log_dir: str = "logs", prefix: str = "api_dry_run_plan") -> str:
    os.makedirs(log_dir, exist_ok=True)
    stamp = bj_now().strftime("%Y%m%d_%H%M%S")
    path = os.path.abspath(os.path.join(log_dir, f"{prefix}_{stamp}.json"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return path


def _format_interval(interval: Optional[Dict[str, Any]]) -> str:
    if not interval:
        return "无"
    return (
        f"{interval.get('room_name')} / 座位{interval.get('seat_num')} / "
        f"{interval.get('start')}-{interval.get('end')} / "
        f"{interval.get('duration_minutes')}分钟"
    )


def format_plan_summary(plan: Dict[str, Any], dry_run: bool = True) -> str:
    if not plan.get("success"):
        label = "API测试" if dry_run else "API方案生成"
        return f"{label}失败: {plan.get('error', '未知原因')}"

    rooms = plan.get("rooms_scanned", [])
    total_intervals = sum(int(room.get("interval_count", 0)) for room in rooms)
    selection = plan.get("selection", {})
    config = plan.get("config", {})

    lines = [
        "API测试完成：只生成方案，未执行预约。" if dry_run else "API方案生成完成：等待确认后才会执行预约。",
        f"有效时段: {config.get('effective_range', '')}",
        f"扫描房间: {len(rooms)} 个，空闲时间段: {total_intervals} 条",
        f"当前房间规则选择: {_format_interval(selection.get('current_room_choice'))}",
        f"当前房间最长时段: {_format_interval(selection.get('current_room_best'))}",
    ]
    warning_summary = _scan_warning_summary(rooms)
    if warning_summary:
        lines.append(warning_summary)
    if config.get("cross_room"):
        lines.append(f"跨房间最佳候选: {_format_interval(selection.get('cross_room_best'))}")
    lines.extend([
        f"最终建议: {_format_interval(selection.get('final_recommendation'))}",
        f"决策: {selection.get('decision_note', '')}",
    ])
    if selection.get("needs_confirmation"):
        lines.append("需要确认: 是，真实预约模式下应弹窗让用户选择。")
    return "\n".join(lines)
