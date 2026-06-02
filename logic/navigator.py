import time
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from core.logger import get_logger

logger = get_logger(__name__)


def enter_room(driver, campus_name, room_name, account: str = ""):
    """进入指定的校区及自习室。"""
    tag = f"[{account}] " if account else ""
    logger.info("🏫 %s进入房间: %s -> %s", tag, campus_name, room_name)

    # 当前页面状态
    try:
        logger.info("📄 %s当前页面: 【%s】 URL: %s", tag, driver.title, driver.current_url[:120])
    except Exception:
        pass

    wait = WebDriverWait(driver, 10)

    try:
        # ── 0. 检测当前页面状态 ──
        seat_els = driver.find_elements(By.CLASS_NAME, "seat-name")
        room_els = driver.find_elements(By.CSS_SELECTOR, ".room-name")
        logger.info("🔍 %s页面状态: seat-name=%d个, room-name=%d个",
                     tag, len(seat_els), len(room_els))

        if seat_els and not room_els:
            logger.info("🔙 %s在座位图但无房间列表，尝试返回...", tag)
            back_btns = driver.find_elements(
                By.XPATH, "//*[contains(text(), '返回') or contains(text(), '房间') or contains(@class, 'back')]")
            logger.info("🔍 %s找到 %d 个返回按钮", tag, len(back_btns))
            for btn in back_btns:
                try:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("✅ %s已点击返回按钮", tag)
                        time.sleep(0.8)
                        break
                except Exception as e:
                    logger.debug("%s返回按钮点击失败: %s", tag, e)

        # ── 1. 切换校区 ──
        try:
            caret = driver.find_elements(By.CSS_SELECTOR, ".el-select__caret")
            logger.info("📌 %s校区下拉框: 找到%d个", tag, len(caret))
            if caret:
                caret[0].click()
                time.sleep(0.3)

            campus_xpath = f"//li/span[text()='{campus_name}']"
            campus_els = driver.find_elements(By.XPATH, campus_xpath)
            logger.info("📌 %s校区选项「%s」: 找到%d个", tag, campus_name, len(campus_els))
            if campus_els:
                wait.until(EC.element_to_be_clickable((By.XPATH, campus_xpath))).click()
                logger.info("✅ %s已选择校区: %s", tag, campus_name)
                time.sleep(1.0)
            else:
                logger.info("ℹ️ %s未找到校区选项，可能已在正确校区", tag)
        except Exception as e:
            logger.warning("⚠️ %s切换校区异常: %s", tag, e)

        # ── 2. 点击自习室 ──
        xpath = (
            f'//*[contains(@class, "room-name") and '
            f'contains(normalize-space(text()), "{room_name}")]'
        )
        logger.info("🔍 %s查找自习室XPath: %s", tag, xpath[:120])

        for attempt in range(5):
            try:
                candidates = driver.find_elements(By.XPATH, xpath)
                logger.info("🔍 %s第%d次: 找到%d个匹配元素", tag, attempt + 1, len(candidates))

                visible = None
                hidden_count = 0
                for i, el in enumerate(candidates):
                    try:
                        if el.is_displayed():
                            visible = el
                            logger.info("✅ %s第%d个元素可见: text=%s", tag, i + 1, el.text[:50])
                            break
                        else:
                            hidden_count += 1
                    except Exception:
                        hidden_count += 1
                        continue

                if not visible:
                    logger.warning("⚠️ %s第%d次: %d个元素均不可见(隐藏%d个)，等待渲染...",
                                    tag, attempt + 1, len(candidates), hidden_count)
                    time.sleep(1.0)
                    continue

                # 滚动到可视区
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                    visible,
                )
                time.sleep(0.3)

                # 点击
                try:
                    logger.info("👆 %s尝试 Selenium click: %s", tag, visible.text[:50])
                    visible.click()
                    logger.info("✅ %s Selenium click 成功", tag)
                except Exception as click_err:
                    logger.warning("⚠️ %s Selenium click失败(%s)，尝试JS click", tag, click_err)
                    driver.execute_script("arguments[0].click();", visible)
                    logger.info("✅ %s JS click 完成", tag)

                logger.info("✅ %s已进入自习室: %s", tag, room_name)
                break

            except StaleElementReferenceException:
                logger.warning("⚠️ %s第%d次: 元素已失效(页面刷新)", tag, attempt + 1)
                time.sleep(0.8)
            except Exception as e:
                logger.error("❌ %s第%d次点击异常: %s (type=%s)",
                              tag, attempt + 1, e, type(e).__name__)
                time.sleep(1.5)
        else:
            logger.error("❌ %s点击自习室连续5次失败！", tag)
            # 输出页面调试信息
            try:
                page_text = driver.find_element(By.TAG_NAME, "body").text[:500]
                logger.error("📄 %s页面内容预览: %s", tag, page_text)
            except Exception:
                pass
            return False

        # ── 3. 确认加载完成 ──
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'seat-name')))
            seat_count = len(driver.find_elements(By.CLASS_NAME, "seat-name"))
            logger.info("✅ %s座位图加载完成: %d个座位", tag, seat_count)
            return True
        except Exception as e:
            logger.warning("⚠️ %s座位图未出现(%s)，尝试点击自选座位...", tag, e)
            try:
                choose_seat = driver.find_element(By.XPATH, "//*[contains(text(), '自选座位')]")
                driver.execute_script("arguments[0].click();", choose_seat)
                time.sleep(1.0)
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'seat-name')))
                logger.info("✅ %s通过「自选座位」进入成功", tag)
                return True
            except Exception as e2:
                logger.error("❌ %s自选座位也失败: %s", tag, e2)
            return False

    except Exception as e:
        logger.error("❌ %s进房异常: %s (type=%s)", tag, e, type(e).__name__)
        return False
