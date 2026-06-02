# logic/scheduler.py
"""
时间分配调度算法

核心职责：根据座位扫描结果，计算最优的座位-时间分配方案。

多账号模式：
  - 将全天时间(如 9:00-21:00)拆分为最多 N 段，每段分配一个账号
  - 贪心策略：每段从当前时间开始，选择持续时间最长的可用座位

单账号模式：
  - 找从目标时间开始持续时间最长的座位
  - 下一段继续从上一段结束时间开始找
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TimeSlot:
    """一个时间段"""
    start: str       # "09:00"
    end: str         # "12:00"


@dataclass
class SeatSlot:
    """一个座位-时间段分配"""
    seat_num: str
    room_name: str
    start: str
    end: str

    @property
    def duration_minutes(self) -> int:
        return _time_to_minutes(self.end) - _time_to_minutes(self.start)


@dataclass
class DaySchedule:
    """
    全天的座位分配方案。

    例如:
      segments = [
        SeatSlot("92",  "三楼智慧研修空间", "09:00", "12:00"),
        SeatSlot("174", "三楼智慧研修空间", "12:00", "18:00"),
        SeatSlot("3",   "四楼阅览室",       "18:00", "21:00"),
      ]
    """
    segments: List[SeatSlot] = field(default_factory=list)
    total_covered_minutes: int = 0
    gaps: List[TimeSlot] = field(default_factory=list)  # 无法覆盖的时间段
    same_room_count: int = 0
    total_seats: int = 0

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def all_same_room(self) -> bool:
        """是否所有座位都在同一房间"""
        if not self.segments:
            return True
        first_room = self.segments[0].room_name
        return all(s.room_name == first_room for s in self.segments)

    def summary(self) -> str:
        lines = []
        for i, s in enumerate(self.segments, 1):
            lines.append(
                f"  第{i}段: 座位{s.seat_num} [{s.room_name}] {s.start}-{s.end} "
                f"({s.duration_minutes}分钟)"
            )
        if self.gaps:
            for g in self.gaps:
                lines.append(f"  ⚠️ 缺口: {g.start}-{g.end}")
        lines.append(
            f"  总计覆盖: {self.total_covered_minutes}分钟, "
            f"{self.segment_count}次换座, "
            f"{'全部同房间' if self.all_same_room else '跨房间'}"
        )
        return "\n".join(lines)


def _time_to_minutes(t: str) -> int:
    """HH:MM → 分钟数"""
    parts = t.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _minutes_to_time(m: int) -> str:
    """分钟数 → HH:MM"""
    return f"{m // 60:02d}:{m % 60:02d}"


def _find_nearest_start(
    availabilities: List[Dict],
    target_time: str,
    tolerance_minutes: int = 30,
) -> List[Dict]:
    """
    在所有可用座位中找到从 target_time（或附近）开始的那些。

    Args:
        availabilities: 扫描结果列表，每个元素是 SeatAvailability 的dict形式
        target_time: 目标开始时间
        tolerance_minutes: 允许的偏差（默认30分钟）
            - 如果 target_time 没有精确匹配，找 ≥target_time 的最近开始时间
            - 如果最近开始时间距 target_time 超过 tolerance_minutes，返回空

    Returns:
        匹配的座位列表（已排序：同房间优先、持续时间最长优先）
    """
    target_mins = _time_to_minutes(target_time)
    max_mins = target_mins + tolerance_minutes

    candidates = []
    for av in availabilities:
        seat_num = av.get("seat_num", av.get("seat", ""))
        room_name = av.get("room_name", "")
        start_times = av.get("start_times", [])
        end_times = av.get("end_times", [])

        if not start_times or not end_times:
            continue

        # 找到 ≥target_time 的最近开始时间
        best_start = None
        best_start_mins = float("inf")
        for s in start_times:
            s_mins = _time_to_minutes(s)
            if s_mins >= target_mins and s_mins <= max_mins and s_mins < best_start_mins:
                best_start = s
                best_start_mins = s_mins

        if best_start is None:
            continue

        # 找到该开始时间之后的最晚结束时间
        best_end = max(end_times, key=_time_to_minutes)
        best_end_mins = _time_to_minutes(best_end)
        if best_end_mins <= best_start_mins:
            continue

        candidates.append({
            "seat_num": str(seat_num),
            "room_name": room_name,
            "start": best_start,
            "end": best_end,
            "duration": best_end_mins - best_start_mins,
        })

    if not candidates:
        return []

    # 排序：持续时间最长优先
    candidates.sort(key=lambda x: x["duration"], reverse=True)
    return candidates


class TimeScheduler:
    """时间分配调度器"""

    @staticmethod
    def find_longest_slot(
        availabilities: List[Dict],
        target_start: str,
        max_end: str = "",
        prefer_room: str = "",
        prefer_seats: list = None,
        priority_mode: str = "longest_first",
    ) -> Optional[SeatSlot]:
        """
        在所有可用座位中，找到从 target_start 开始、持续时间最长的那个。

        Args:
            availabilities: 扫描结果列表
            target_start: 目标开始时间，如 "09:00"
            max_end: 最大结束时间限制，如 "21:00"（空=不限）
            prefer_room: 优先的房间名（空=不限制）
            prefer_seats: 优先座位号列表（如 ["001","054","169"]）
            priority_mode: "prefer_first" 优先座位优先, "longest_first" 算法优先

        Returns:
            SeatSlot 或 None
        """
        candidates = _find_nearest_start(availabilities, target_start)
        if not candidates:
            return None

        # 如果指定了最大结束时间，裁剪超出的部分
        if max_end:
            max_end_mins = _time_to_minutes(max_end)
            for c in candidates:
                if _time_to_minutes(c["end"]) > max_end_mins:
                    c["end"] = max_end
                    c["duration"] = max_end_mins - _time_to_minutes(c["start"])

        def _pick_best(pool):
            """从候选中选最优：同房间优先，然后持续时间最长"""
            if prefer_room:
                same = [c for c in pool if c["room_name"] == prefer_room]
                if same:
                    best = max(same, key=lambda x: x["duration"])
                    return SeatSlot(
                        seat_num=best["seat_num"],
                        room_name=best["room_name"],
                        start=best["start"],
                        end=best["end"],
                    )
            best = max(pool, key=lambda x: x["duration"])
            return SeatSlot(
                seat_num=best["seat_num"],
                room_name=best["room_name"],
                start=best["start"],
                end=best["end"],
            )

        # ── 优先座位模式 ──
        if priority_mode == "prefer_first" and prefer_seats:
            # 按优先列表顺序尝试
            for pref in prefer_seats:
                # 去前导零匹配（用户填001，扫描结果可能是1或001）
                match = None
                for c in candidates:
                    c_seat = str(c["seat_num"])
                    # 标准化比较：都去掉前导零
                    c_norm = str(int(c_seat)) if c_seat.isdigit() else c_seat
                    p_norm = str(int(pref)) if str(pref).isdigit() else str(pref)
                    if c_norm == p_norm:
                        match = c
                        break
                if match:
                    logger.info("★ 优先座位 %s 可用！", pref)
                    return SeatSlot(
                        seat_num=match["seat_num"],
                        room_name=match["room_name"],
                        start=match["start"],
                        end=match["end"],
                    )
            # 优先座位都不匹配 → 回退到算法
            logger.info("优先座位均不可用，回退到算法选择")

        # ── 算法模式 / 回退 ──
        return _pick_best(candidates)

    @staticmethod
    def partition_day(
        availabilities: List[Dict],
        day_start: str = "09:00",
        day_end: str = "21:00",
        max_segments: int = 3,
        prefer_room: str = "",
        prefer_seats: list = None,
        priority_mode: str = "longest_first",
    ) -> DaySchedule:
        """
        核心算法：将全天时间拆分为最多 max_segments 段。

        贪心策略：
          1. current_time = day_start
          2. 循环 (最多 max_segments 次):
             a. 在 current_time 之后找可用持续时间最长的座位
             b. 如果找不到精确匹配的 current_time，向前搜索最近的可用时间（容忍30分钟）
             c. 记录分配
             d. current_time = 分配.end
             e. 如果 current_time >= day_end: 完成
          3. 返回分配方案

        Args:
            availabilities: 座位扫描结果
            day_start: 全天开始时间，如 "09:00"
            day_end: 全天结束时间，如 "21:00"
            max_segments: 最多拆分为几段（即几个账号）
            prefer_room: 优先房间名

        Returns:
            DaySchedule 对象
        """
        schedule = DaySchedule()
        day_start_mins = _time_to_minutes(day_start)
        day_end_mins = _time_to_minutes(day_end)
        total_desired = day_end_mins - day_start_mins

        current_time = day_start

        for seg_idx in range(max_segments):
            if _time_to_minutes(current_time) >= day_end_mins:
                break  # 已覆盖全部时间

            slot = TimeScheduler.find_longest_slot(
                availabilities,
                target_start=current_time,
                max_end=day_end,
                prefer_room=prefer_room,
                prefer_seats=prefer_seats,
                priority_mode=priority_mode,
            )

            if slot is None:
                # 找不到精确匹配的开始时间，尝试扩大搜索范围
                logger.info(
                    "⚠️ 无法从 %s 开始找到座位，尝试最近可用时间...",
                    current_time,
                )
                # 尝试：只要开始时间在 current_time 之后的都行（不限制tolerance）
                slot = TimeScheduler.find_longest_slot(
                    availabilities,
                    target_start=current_time,
                    max_end=day_end,
                    prefer_room=prefer_room,
                    prefer_seats=prefer_seats,
                    priority_mode=priority_mode,
                )

                if slot is None:
                    # 确实找不到，记录缺口
                    gap_start = current_time
                    gap_end = day_end
                    if _time_to_minutes(gap_start) < day_end_mins:
                        schedule.gaps.append(
                            TimeSlot(start=gap_start, end=gap_end)
                        )
                    break

            schedule.segments.append(slot)
            current_time = slot.end
            logger.info(
                "📋 第%d段: 座位%s [%s] %s-%s (%d分钟)",
                seg_idx + 1, slot.seat_num, slot.room_name,
                slot.start, slot.end, slot.duration_minutes,
            )

        # 计算统计
        schedule.total_covered_minutes = sum(s.duration_minutes for s in schedule.segments)
        schedule.total_seats = len(set(s.seat_num for s in schedule.segments))
        rooms = set(s.room_name for s in schedule.segments)
        schedule.same_room_count = 1 if len(rooms) == 1 else len(rooms)

        logger.info(
            "📊 分配完成: 覆盖 %d/%d 分钟, %d 段, %d 个房间",
            schedule.total_covered_minutes, total_desired,
            schedule.segment_count, schedule.same_room_count,
        )

        return schedule

    @staticmethod
    def select_best_schedule(
        schedules: List[DaySchedule],
    ) -> DaySchedule:
        """
        从多个可行方案中选择最优的。

        优先级：
          1. 覆盖时间最长
          2. 换座次数最少
          3. 全部同房间

        Args:
            schedules: 候选方案列表

        Returns:
            最优方案
        """
        if not schedules:
            return DaySchedule()

        def score(s: DaySchedule) -> Tuple[int, int, int]:
            # (覆盖时间, -换座次数, 全部同房间)
            return (
                s.total_covered_minutes,
                -s.segment_count,
                1 if s.all_same_room else 0,
            )

        schedules.sort(key=score, reverse=True)
        best = schedules[0]
        logger.info(
            "🏆 最优方案: 覆盖 %d 分钟, %d 段, %s",
            best.total_covered_minutes,
            best.segment_count,
            "全部同房间" if best.all_same_room else "跨房间",
        )
        return best

    @staticmethod
    def merge_consecutive(schedule: DaySchedule) -> DaySchedule:
        """
        合并同一座位可连续使用的段。
        如果同一座位的两段时间相邻（前一段结束=后一段开始），合并为一段。
        """
        if not schedule.segments:
            return schedule

        merged = []
        current = schedule.segments[0]

        for next_slot in schedule.segments[1:]:
            if (
                current.seat_num == next_slot.seat_num
                and current.room_name == next_slot.room_name
                and current.end == next_slot.start
            ):
                # 合并
                current = SeatSlot(
                    seat_num=current.seat_num,
                    room_name=current.room_name,
                    start=current.start,
                    end=next_slot.end,
                )
            else:
                merged.append(current)
                current = next_slot

        merged.append(current)

        new_schedule = DaySchedule(
            segments=merged,
            total_covered_minutes=sum(s.duration_minutes for s in merged),
            gaps=schedule.gaps,
            same_room_count=len(set(s.room_name for s in merged)),
            total_seats=len(set(s.seat_num for s in merged)),
        )
        return new_schedule


def build_availability_from_scan(
    scan_results: List,
    room_name: str = "",
) -> List[Dict]:
    """
    将 SeatAvailability 对象列表转换为 scheduler 需要的 dict 格式。
    兼容 scanner.py 和 booker.py 的返回格式。
    """
    result = []
    for item in scan_results:
        if isinstance(item, dict):
            av = item
        else:
            av = {
                "seat_num": item.seat_num,
                "room_name": getattr(item, "room_name", room_name),
                "available": item.available,
                "start_times": item.start_times,
                "end_times": item.end_times,
            }

        if av.get("available") or (av.get("start_times") and av.get("end_times")):
            result.append(av)

    return result
