# logic/booking_manager.py
"""
预约管理器

核心职责：查看/取消已有预约。需要导航到「我的预约」页面进行操作。

⚠️ 注意：以下选择器基于对 Vue.js + Element UI 架构的推断。
    运行时可能需要根据实际 DOM 结构微调。请在实际浏览器中验证。
"""

import time
import re
from typing import Optional, Dict
from dataclasses import dataclass

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from core.logger import get_logger

logger = get_logger(__name__)


# ── 导航到「我的预约」页面的策略（按优先级依次尝试） ──
_MY_BOOKINGS_NAV_STRATEGIES = [
    # 策略1: 点击header中的用户下拉菜单 → 找「我的预约」
    {
        "name": "header-dropdown",
        "steps": [
            # 步骤1: 点击header中的用户区域触发下拉
            {
                "action": "click",
                "selectors": [
                    (By.CSS_SELECTOR, ".header-username"),
                    (By.CSS_SELECTOR, ".user-dropdown"),
                    (By.CSS_SELECTOR, ".el-dropdown"),
                    (By.CSS_SELECTOR, "[class*='user']"),
                ],
            },
            # 步骤2: 点击「我的预约」菜单项
            {
                "action": "click_text",
                "texts": ["我的预约", "预约记录", "当前预约", "个人中心"],
                "fallback_selectors": [
                    (By.XPATH, "//*[contains(text(), '我的预约')]"),
                    (By.XPATH, "//*[contains(text(), '预约记录')]"),
                    (By.XPATH, "//li[contains(text(), '预约')]"),
                ],
            },
        ],
    },
    # 策略2: 直接修改URL hash（Vue Router）
    {
        "name": "hash-navigate",
        "urls": [
            "#/my-bookings",
            "#/my",
            "#/reservations",
            "#/user/reservations",
            "#/profile",
            "#/personal",
        ],
    },
    # 策略3: 通过顶部导航栏找「我的」
    {
        "name": "top-nav",
        "steps": [
            {
                "action": "click_text",
                "texts": ["我的", "个人中心", "我的预约"],
                "fallback_selectors": [
                    (By.CSS_SELECTOR, ".nav-bar a"),
                    (By.CSS_SELECTOR, ".header-nav a"),
                    (By.XPATH, "//a[contains(text(), '我的')]"),
                    (By.XPATH, "//span[contains(text(), '我的')]"),
                ],
            },
        ],
    },
]

# ── 取消按钮选择器 ──
_CANCEL_BTN_SELECTORS = [
    (By.XPATH, "//button[contains(text(), '取消预约')]"),
    (By.XPATH, "//span[contains(text(), '取消预约')]"),
    (By.XPATH, "//*[contains(@class, 'cancel')]"),
    (By.CSS_SELECTOR, ".cancel-btn"),
    (By.CSS_SELECTOR, ".el-button--danger"),
    (By.XPATH, "//button[contains(text(), '取消')]"),
]

# ── 确认弹窗按钮 ──
_CONFIRM_CANCEL_SELECTORS = [
    (By.XPATH, "//button[contains(text(), '确定')]"),
    (By.XPATH, "//button[contains(text(), '确认')]"),
    (By.CSS_SELECTOR, ".el-message-box__btns .el-button--primary"),
    (By.CSS_SELECTOR, ".el-dialog__footer .el-button--primary"),
]

# ── 预约信息选择器（在「我的预约」页面中） ──
_BOOKING_INFO_SELECTORS = [
    (By.CSS_SELECTOR, ".booking-item"),
    (By.CSS_SELECTOR, ".reservation-item"),
    (By.CSS_SELECTOR, ".booking-card"),
    (By.CSS_SELECTOR, ".el-card"),
    (By.CSS_SELECTOR, "[class*='booking']"),
]


@dataclass
class BookingInfo:
    """预约信息"""
    seat_num: str = ""
    room_name: str = ""
    start_time: str = ""
    end_time: str = ""
    status: str = ""   # "有效" / "已取消" / "已完成"
    raw_text: str = ""  # 原始页面文本

    @property
    def is_active(self) -> bool:
        return self.status in ("有效", "使用中", "待签到", "")

    @property
    def end_minutes(self) -> int:
        """结束时间转分钟数"""
        if not self.end_time:
            return 0
        parts = self.end_time.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])


def _try_find_and_click(driver, selectors, timeout=2.0) -> bool:
    """尝试多个选择器找到元素并点击"""
    for by, sel in selectors:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, sel))
            )
            driver.execute_script("arguments[0].click();", el)
            return True
        except (TimeoutException, NoSuchElementException):
            continue
    return False


def _try_find_text_and_click(driver, texts, timeout=2.0) -> bool:
    """通过文本内容找到元素并点击"""
    for text in texts:
        try:
            xpath = f"//*[contains(text(), '{text}')]"
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            driver.execute_script("arguments[0].click();", el)
            return True
        except (TimeoutException, NoSuchElementException):
            continue
    return False


def _extract_time_from_text(text: str) -> tuple:
    """从文本中提取开始和结束时间，如 '09:00-12:00' → ('09:00', '12:00')"""
    # 匹配 HH:MM - HH:MM 或 HH:MM~HH:MM
    pattern = r"(\d{1,2}:\d{2})\s*[-～~]\s*(\d{1,2}:\d{2})"
    match = re.search(pattern, text)
    if match:
        return match.group(1), match.group(2)
    return "", ""


def _extract_seat_from_text(text: str) -> str:
    """从文本中提取座位号"""
    # 匹配 "座位号: 92" / "座位：92" / "#92" 等
    patterns = [
        r"座位[号\s]*[：:]\s*(\d+)",
        r"座位\s*(\d+)",
        r"#(\d+)",
        r"(\d+)号座",
    ]
    for p in patterns:
        match = re.search(p, text)
        if match:
            return match.group(1)
    return ""


class BookingManager:
    """预约管理器"""

    def __init__(self, driver, account: str = ""):
        self.driver = driver
        self.account = account or "unknown"

    # ───────────────────── 导航到我的预约 ─────────────────────

    def navigate_to_my_bookings(self) -> bool:
        """
        导航到「我的预约」页面。
        用多种策略依次尝试，第一个成功就返回。

        Returns:
            是否成功导航
        """
        for strategy in _MY_BOOKINGS_NAV_STRATEGIES:
            name = strategy["name"]
            logger.info("[%s] 🔍 尝试导航策略: %s", self.account, name)

            try:
                if name == "hash-navigate":
                    # 直接修改URL
                    base_url = self.driver.current_url.split("#")[0]
                    for url_path in strategy["urls"]:
                        try:
                            target = base_url + url_path
                            logger.debug("[%s]   尝试URL: %s", self.account, target)
                            self.driver.get(target)
                            time.sleep(1.5)
                            # 检查页面是否有内容（不是空白）
                            body_text = self.driver.find_element(By.TAG_NAME, "body").text
                            if body_text and len(body_text) > 20:
                                logger.info("[%s] ✅ URL导航成功: %s", self.account, target)
                                return True
                        except Exception:
                            continue

                elif name in ("header-dropdown", "top-nav"):
                    for step in strategy.get("steps", []):
                        action = step.get("action", "")
                        if action == "click":
                            clicked = _try_find_and_click(
                                self.driver, step.get("selectors", []), timeout=2.0
                            )
                            if clicked:
                                time.sleep(0.5)
                        elif action == "click_text":
                            clicked = _try_find_text_and_click(
                                self.driver, step.get("texts", []), timeout=2.0
                            )
                            if not clicked:
                                # 回退到CSS选择器
                                clicked = _try_find_and_click(
                                    self.driver,
                                    step.get("fallback_selectors", []),
                                    timeout=1.5,
                                )
                            if clicked:
                                time.sleep(1.0)

                    # 检查是否成功到了预约页面
                    time.sleep(0.5)
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text or ""
                    if any(
                        kw in body_text
                        for kw in ("我的预约", "预约记录", "取消预约", "当前预约")
                    ):
                        logger.info("[%s] ✅ 导航到我的预约成功 (策略: %s)", self.account, name)
                        return True

            except Exception as e:
                logger.debug("[%s] 导航策略 %s 失败: %s", self.account, name, e)
                continue

        logger.error("[%s] ❌ 所有导航策略都失败了！需要手动确认「我的预约」入口。", self.account)
        return False

    # ───────────────────── 获取当前预约 ─────────────────────

    def get_current_booking(self) -> Optional[BookingInfo]:
        """
        读取当前有效预约信息。

        Returns:
            BookingInfo 或 None（无有效预约）
        """
        try:
            # 尝试找到预约列表
            booking_elements = []
            for by, sel in _BOOKING_INFO_SELECTORS:
                try:
                    els = self.driver.find_elements(by, sel)
                    if els:
                        booking_elements = els
                        break
                except Exception:
                    continue

            if not booking_elements:
                # 如果没有单独的卡片，直接解析整个页面
                body_text = self.driver.find_element(By.TAG_NAME, "body").text or ""
                if "暂无预约" in body_text or "无预约记录" in body_text:
                    logger.info("[%s] ℹ️ 当前无有效预约", self.account)
                    return None

                return self._parse_booking_from_text(body_text)

            # 解析第一个预约（通常一个账号只有一个）
            for el in booking_elements:
                try:
                    text = el.text.strip()
                    if text:
                        return self._parse_booking_from_text(text)
                except Exception:
                    continue

            return None

        except Exception as e:
            logger.error("[%s] ❌ 获取预约信息失败: %s", self.account, e)
            return None

    def _parse_booking_from_text(self, text: str) -> Optional[BookingInfo]:
        """从文本中解析预约信息"""
        if not text or len(text) < 5:
            return None

        # 跳过已取消的
        if "已取消" in text or "已完成" in text:
            logger.info("[%s] ℹ️ 预约已过期: %s", self.account, text[:100])
            return None

        start_time, end_time = _extract_time_from_text(text)
        seat_num = _extract_seat_from_text(text)

        # 判断状态
        status = "有效"
        if "已取消" in text:
            status = "已取消"
        elif "已完成" in text:
            status = "已完成"
        elif "待签到" in text:
            status = "待签到"

        info = BookingInfo(
            seat_num=seat_num,
            start_time=start_time,
            end_time=end_time,
            status=status,
            raw_text=text,
        )
        logger.info(
            "[%s] 📋 当前预约: 座位%s %s-%s (%s)",
            self.account, seat_num, start_time, end_time, status,
        )
        return info

    # ───────────────────── 取消预约 ─────────────────────

    def cancel_booking(self) -> bool:
        """
        取消当前预约。

        流程:
          1. 在「我的预约」页面找到取消按钮
          2. 点击取消
          3. 在确认弹窗中点击确定
          4. 等待结果反馈

        Returns:
            是否成功取消
        """
        logger.info("[%s] 🗑️ 正在取消当前预约...", self.account)

        try:
            # 步骤1: 点击取消按钮
            cancel_clicked = False
            for by, sel in _CANCEL_BTN_SELECTORS:
                try:
                    els = self.driver.find_elements(by, sel)
                    for el in els:
                        if el.is_displayed() and el.is_enabled():
                            self.driver.execute_script("arguments[0].click();", el)
                            cancel_clicked = True
                            logger.info("[%s] 🔘 已点击取消按钮", self.account)
                            break
                    if cancel_clicked:
                        break
                except Exception:
                    continue

            if not cancel_clicked:
                logger.error(
                    "[%s] ❌ 找不到取消预约按钮！需要运行时确认选择器。",
                    self.account,
                )
                return False

            # 步骤2: 等待确认弹窗并点击确定
            time.sleep(0.5)
            for by, sel in _CONFIRM_CANCEL_SELECTORS:
                try:
                    el = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    self.driver.execute_script("arguments[0].click();", el)
                    logger.info("[%s] ✅ 已在确认弹窗中点击确定", self.account)
                    break
                except (TimeoutException, NoSuchElementException):
                    continue
            else:
                logger.warning(
                    "[%s] ⚠️ 未弹出确认弹窗，取消可能已直接生效",
                    self.account,
                )

            # 步骤3: 等待结果
            time.sleep(1.0)
            body_text = self.driver.find_element(By.TAG_NAME, "body").text or ""
            if "取消成功" in body_text or "暂无预约" in body_text:
                logger.info("[%s] ✅ 预约已成功取消", self.account)
                return True

            # 再次检查是否还有预约
            remaining = self.get_current_booking()
            if remaining and remaining.is_active:
                logger.warning("[%s] ⚠️ 取消后仍检测到有效预约，可能取消失败", self.account)
                return False

            logger.info("[%s] ✅ 预约已取消（未检测到剩余预约）", self.account)
            return True

        except Exception as e:
            logger.error("[%s] ❌ 取消预约异常: %s", self.account, e)
            return False

    # ───────────────────── 返回座位图 ─────────────────────

    def return_to_seat_grid(self) -> bool:
        """
        从「我的预约」页面返回座位图页面。

        Returns:
            是否成功返回
        """
        logger.info("[%s] 🔙 正在返回座位图...", self.account)

        strategies = [
            # 策略1: 点击「自选座位」
            {
                "action": "click_text",
                "texts": ["自选座位", "选座", "座位预约", "开始预约"],
            },
            # 策略2: URL hash
            {
                "action": "hash",
                "urls": ["#/seat", "#/home", "#/index", "#/"],
            },
        ]

        for strategy in strategies:
            try:
                if strategy["action"] == "click_text":
                    for text in strategy["texts"]:
                        try:
                            xpath = f"//*[contains(text(), '{text}')]"
                            el = WebDriverWait(self.driver, 2).until(
                                EC.element_to_be_clickable((By.XPATH, xpath))
                            )
                            self.driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.8)
                            if self.driver.find_elements(By.CLASS_NAME, "seat-name"):
                                logger.info("[%s] ✅ 已返回座位图", self.account)
                                return True
                        except Exception:
                            continue

                elif strategy["action"] == "hash":
                    base = self.driver.current_url.split("#")[0]
                    for url in strategy["urls"]:
                        try:
                            self.driver.get(base + url)
                            time.sleep(1)
                            if self.driver.find_elements(By.CLASS_NAME, "seat-name"):
                                logger.info("[%s] ✅ 已返回座位图", self.account)
                                return True
                        except Exception:
                            continue
            except Exception:
                continue

        logger.warning("[%s] ⚠️ 无法自动返回座位图，请手动操作", self.account)
        return False
