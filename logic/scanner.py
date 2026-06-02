# logic/scanner.py
"""
座位可用时间扫描器

核心职责：遍历座位图，读取每个座位的可用时间段。
由于网站不直接在座位图上显示可用状态，必须逐个点击座位来检查。
"""

import time
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.logger import get_logger
from logic.navigator import enter_room

logger = get_logger(__name__)

# ── 座位不可用的提示关键词 ──
_SEAT_UNAVAILABLE_KEYWORDS = (
    "不可用", "没有可用时间", "没有可约时间", "约满",
    "不可预约", "当前不可用", "无法预约", "已满", "已被",
    "没有可用", "已被他人预约",
)

# ── 时间选择弹窗出现的选择器 ──
_RESERVE_BOX_SELECTOR = (By.CLASS_NAME, "reserve-box")
_SEAT_NAME_SELECTOR = (By.CLASS_NAME, "seat-name")
_TIMES_ROLL_XPATH = '//div[@class="times-roll"]'

# ── 扫描时的超时设置 ──
_POPUP_TIMEOUT = 2.0       # 等待弹窗出现的超时
_TOAST_CHECK_INTERVAL = 0.05  # toast轮询间隔
_CLOSE_RETRY = 3            # 关闭弹窗重试次数


@dataclass
class SeatAvailability:
    """单个座位的可用时间信息"""
    seat_num: str
    room_name: str = ""
    available: bool = False
    start_times: List[str] = field(default_factory=list)
    end_times: List[str] = field(default_factory=list)
    error_msg: str = ""

    @property
    def longest_slot(self) -> Optional[Tuple[str, str]]:
        """返回该座位可用的最长连续时间段 (start, end)，若无则返回 None"""
        if not self.available or not self.start_times or not self.end_times:
            return None
        # 找到 end_times 中最晚的那个（持续时间最长）
        best_end = max(self.end_times, key=_time_to_minutes)
        return (self.start_times[0], best_end)

    def get_slots_from(self, target_start: str) -> List[Tuple[str, str]]:
        """获取从 target_start 开始的所有可用时间段"""
        slots = []
        target_mins = _time_to_minutes(target_start)
        for s in self.start_times:
            s_mins = _time_to_minutes(s)
            if s_mins >= target_mins:
                # 找到这个开始时间对应的最长结束时间
                best_end = max(self.end_times, key=_time_to_minutes)
                end_mins = _time_to_minutes(best_end)
                if end_mins > s_mins:
                    slots.append((s, best_end))
        return slots


def _time_to_minutes(t: str) -> int:
    """将 HH:MM 格式转换为分钟数"""
    parts = t.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _parse_time_label(label_text: str) -> Optional[str]:
    """从label文本中提取时间字符串，如 '08:00'"""
    text = label_text.strip()
    if ":" in text and len(text) <= 6:
        parts = text.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return text
    return None


class SeatScanner:
    """座位可用时间扫描器"""

    def __init__(self, driver, account: str = ""):
        self.driver = driver
        self.account = account or "scanner"
        self.wait = WebDriverWait(driver, 3)

        # 导入 booker 的实例方法来复用fast-fail和弹窗关闭逻辑
        from logic.booker import SeatBooker
        self._booker = SeatBooker(driver, account=self.account)

    # ───────────────────── 时间列读取 ─────────────────────

    def read_available_times(self) -> Dict[str, List[str]]:
        """
        读取当前已打开的时间选择弹窗中所有可选时间。

        返回格式:
          {"starts": ["08:00","08:30",...], "ends": ["12:00","12:30",...]}

        如果弹窗不存在或时间列不可读，返回空列表。
        """
        result = {"starts": [], "ends": []}
        try:
            # 列1 = 开始时间, 列2 = 结束时间
            for col_idx, key in [(1, "starts"), (2, "ends")]:
                xpath = f"({_TIMES_ROLL_XPATH})[{col_idx}]//label"
                labels = self.driver.find_elements(By.XPATH, xpath)
                for label in labels:
                    try:
                        if not label.is_displayed():
                            continue
                        text = label.text.strip()
                        time_str = _parse_time_label(text)
                        if time_str:
                            result[key].append(time_str)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("[%s] 读取时间列异常: %s", self.account, e)

        # 对时间排序
        result["starts"].sort(key=_time_to_minutes)
        result["ends"].sort(key=_time_to_minutes)
        return result

    def _read_first_available_start(self) -> Optional[str]:
        """读取第一个可用的开始时间（用于快速检查）"""
        try:
            xpath = f"({_TIMES_ROLL_XPATH})[1]//label"
            labels = self.driver.find_elements(By.XPATH, xpath)
            for label in labels:
                try:
                    if not label.is_displayed():
                        continue
                    time_str = _parse_time_label(label.text.strip())
                    if time_str:
                        return time_str
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ───────────────────── 单座位检查 ─────────────────────

    def check_seat(self, seat_num: str, room_name: str = "") -> SeatAvailability:
        """
        点击单个座位并读取其可用时间。

        Args:
            seat_num: 座位号（如 "92"）
            room_name: 当前房间名称（用于结果标记）

        Returns:
            SeatAvailability 对象
        """
        result = SeatAvailability(seat_num=seat_num, room_name=room_name)

        # 规范化座位号（去前导零）
        clean_seat = str(int(seat_num)) if str(seat_num).isdigit() else str(seat_num)

        try:
            # 1. 确保没有残留弹窗
            self._booker._cleanup_all_popups()
            time.sleep(0.05)

            # 2. 点击座位
            xpath = f'//div[contains(@class, "seat-name") and normalize-space(text())="{clean_seat}"]'
            try:
                seat_elem = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", seat_elem
                )
                try:
                    seat_elem.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", seat_elem)
            except Exception:
                result.error_msg = f"座位 {seat_num} 找不到或不可点击"
                return result

            # 3. 快速失败检测：先检查 page_source 是否有失败关键词
            time.sleep(0.15)  # 给页面一点反应时间
            ps = self.driver.page_source or ""
            fast_fail = next(
                (kw for kw in _SEAT_UNAVAILABLE_KEYWORDS if kw in ps), None
            )
            if fast_fail:
                result.error_msg = f"座位 {seat_num} 不可用: {fast_fail}"
                # 可能有残留弹窗需要关闭
                if self.driver.find_elements(*_RESERVE_BOX_SELECTOR):
                    self._booker.close_popup()
                return result

            # 4. 检查 toast 提示
            msg = self._booker._get_latest_ui_message()
            if msg:
                hit_kw = next(
                    (kw for kw in _SEAT_UNAVAILABLE_KEYWORDS if kw in msg), None
                )
                if hit_kw:
                    result.error_msg = f"座位 {seat_num} 不可用: {msg}"
                    if self.driver.find_elements(*_RESERVE_BOX_SELECTOR):
                        self._booker.close_popup()
                    return result

            # 5. 等待预约弹窗出现
            start_wait = time.time()
            popup_found = False
            while time.time() - start_wait < _POPUP_TIMEOUT:
                # 持续检查 toast
                msg = self._booker._get_latest_ui_message()
                if msg:
                    hit_kw = next(
                        (kw for kw in _SEAT_UNAVAILABLE_KEYWORDS if kw in msg), None
                    )
                    if hit_kw:
                        result.error_msg = f"座位 {seat_num}: {msg}"
                        if self.driver.find_elements(*_RESERVE_BOX_SELECTOR):
                            self._booker.close_popup()
                        return result

                if self.driver.find_elements(*_RESERVE_BOX_SELECTOR):
                    popup_found = True
                    break
                time.sleep(_TOAST_CHECK_INTERVAL)

            if not popup_found:
                result.error_msg = f"座位 {seat_num} 点击后无弹窗"
                return result

            # 6. 读取时间列
            time.sleep(0.2)  # 等时间列渲染完成
            times = self.read_available_times()
            if times["starts"] and times["ends"]:
                result.available = True
                result.start_times = times["starts"]
                result.end_times = times["ends"]
            else:
                result.error_msg = f"座位 {seat_num} 弹窗内无可用时间"

            # 7. 关闭弹窗
            self._booker.close_popup()

        except Exception as e:
            result.error_msg = f"座位 {seat_num} 扫描异常: {e}"
            try:
                self._booker.close_popup()
            except Exception:
                pass

        return result

    # ───────────────────── 全房间扫描 ─────────────────────

    def scan_room(
        self,
        room_name: str,
        campus_name: str = "",
        sample_size: int = 0,
    ) -> List[SeatAvailability]:
        """
        扫描指定房间的所有座位。

        Args:
            room_name: 房间名称（如 "三楼智慧研修空间"）
            campus_name: 校区名称（如已在校区页面可省略）
            sample_size: 抽查模式：>0 时随机抽查 N 个座位（用于快速评估）

        Returns:
            可用座位列表（仅包含 available=True 的座位）
        """
        # 确保在目标房间
        if campus_name:
            if not enter_room(self.driver, campus_name, room_name, account=self.account):
                logger.error("[%s] 无法进入房间: %s", self.account, room_name)
                return []

        # 获取所有座位号
        try:
            seat_elems = self.driver.find_elements(*_SEAT_NAME_SELECTOR)
        except Exception:
            logger.error("[%s] 找不到座位元素", self.account)
            return []

        if not seat_elems:
            logger.warning("[%s] 房间 %s 无座位", self.account, room_name)
            return []

        all_seats = []
        for el in seat_elems:
            try:
                num = el.text.strip()
                if num:
                    # 去前导零
                    clean = str(int(num)) if num.isdigit() else num
                    all_seats.append(clean)
            except Exception:
                continue

        # 去重（有些座位可能被多个元素表示）
        all_seats = list(dict.fromkeys(all_seats))

        # 随机抽查模式
        if sample_size > 0 and len(all_seats) > sample_size:
            scan_seats = random.sample(all_seats, sample_size)
            logger.info(
                "[%s] 🔍 抽查模式：从 %d 个座位中随机抽查 %d 个",
                self.account, len(all_seats), sample_size,
            )
        else:
            scan_seats = all_seats
            logger.info(
                "[%s] 🔍 开始扫描 %s 全部 %d 个座位...",
                self.account, room_name, len(scan_seats),
            )

        # 逐个扫描
        available_results = []
        for i, seat_num in enumerate(scan_seats, 1):
            logger.debug("[%s] 扫描座位 %s (%d/%d)...", self.account, seat_num, i, len(scan_seats))

            result = self.check_seat(seat_num, room_name)
            if result.available:
                available_results.append(result)
                logger.info(
                    "[%s] ✅ 座位 %s 可用: %d 个开始时间, %d 个结束时间",
                    self.account, seat_num,
                    len(result.start_times), len(result.end_times),
                )
            else:
                logger.debug("[%s] ❌ 座位 %s: %s", self.account, seat_num, result.error_msg)

        logger.info(
            "[%s] 📊 %s 扫描完成: %d/%d 可用",
            self.account, room_name, len(available_results), len(scan_seats),
        )

        return available_results

    # ───────────────────── 跨房间扫描 ─────────────────────

    def scan_all_rooms(
        self,
        room_names: List[str],
        campus_name: str,
        sample_size: int = 0,
    ) -> Dict[str, List[SeatAvailability]]:
        """
        扫描多个房间。

        Args:
            room_names: 房间名称列表，按优先级排序（第一个最优先）
            campus_name: 校区名称
            sample_size: 每个房间的抽查数量，0=全扫

        Returns:
            {room_name: [SeatAvailability, ...]}
        """
        results = {}
        for room_name in room_names:
            logger.info("[%s] 🏫 正在扫描房间: %s", self.account, room_name)
            avail = self.scan_room(room_name, campus_name, sample_size)
            results[room_name] = avail

            # 检查是否需要进入下一个房间（有些切换后需要重新等加载）
            time.sleep(0.3)

        total_avail = sum(len(v) for v in results.values())
        logger.info(
            "[%s] 📊 跨房间扫描完成: %d 个房间共 %d 个可用座位",
            self.account, len(room_names), total_avail,
        )
        return results

    # ───────────────────── 快速扫描（只检查是否可点） ─────────────────────

    def quick_scan_room(self, room_name: str) -> List[str]:
        """
        快速扫描：只返回有可用时间的座位号列表，不读取具体时间。
        这比全扫描快很多，适合单账号模式先找到目标座位。
        """
        # 确保在目标房间
        try:
            seat_elems = self.driver.find_elements(*_SEAT_NAME_SELECTOR)
        except Exception:
            return []

        all_seats = []
        for el in seat_elems:
            try:
                num = el.text.strip()
                if num:
                    clean = str(int(num)) if num.isdigit() else num
                    all_seats.append(clean)
            except Exception:
                continue
        all_seats = list(dict.fromkeys(all_seats))

        available_seats = []
        for i, seat_num in enumerate(all_seats, 1):
            logger.debug("[%s] 快速扫描 %s (%d/%d)...", self.account, seat_num, i, len(all_seats))

            try:
                self._booker._cleanup_all_popups()
                time.sleep(0.03)

                clean_seat = str(int(seat_num)) if str(seat_num).isdigit() else str(seat_num)
                xpath = f'//div[contains(@class, "seat-name") and normalize-space(text())="{clean_seat}"]'
                try:
                    seat_elem = WebDriverWait(self.driver, 1.5).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    self.driver.execute_script("arguments[0].click();", seat_elem)
                except Exception:
                    continue

                time.sleep(0.1)

                # 快速失败
                ps = self.driver.page_source or ""
                if any(kw in ps for kw in _SEAT_UNAVAILABLE_KEYWORDS):
                    if self.driver.find_elements(*_RESERVE_BOX_SELECTOR):
                        self._booker.close_popup()
                    continue

                msg = self._booker._get_latest_ui_message()
                if msg and any(kw in msg for kw in _SEAT_UNAVAILABLE_KEYWORDS):
                    if self.driver.find_elements(*_RESERVE_BOX_SELECTOR):
                        self._booker.close_popup()
                    continue

                # 等弹窗
                popup_found = False
                start_w = time.time()
                while time.time() - start_w < 1.5:
                    if self.driver.find_elements(*_RESERVE_BOX_SELECTOR):
                        popup_found = True
                        break
                    time.sleep(0.05)

                if popup_found:
                    # 只读第一个开始时间确认可用即可
                    first_start = self._read_first_available_start()
                    if first_start:
                        available_seats.append(seat_num)
                    self._booker.close_popup()

            except Exception:
                try:
                    self._booker.close_popup()
                except Exception:
                    pass
                continue

        logger.info(
            "[%s] 快速扫描 %s: %d/%d 可用",
            self.account, room_name, len(available_seats), len(all_seats),
        )

        return available_seats
