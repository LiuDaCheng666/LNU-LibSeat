"""REST API 客户端 — 直接调用 libseat 后端接口，绕过 Selenium 点击。

发现的 API 端点（base: http://libseat.lnu.edu.cn/rest/v2/）:
  GET  /room/stats2/{buildingId}/{date}            — 全校区房间统计 (free/total)
  GET  /room/layoutByDate/{roomId}/{date}           — 房间座位布局（所有座位ID）
  GET  /startTimesForSeat/{seatId}/{date}           — 可用开始时间
  GET  /endTimesForSeat/{seatId}/{date}/{start}     — 可用结束时间
  POST /room/floors/{buildingId}                    — 楼层列表

认证: URL 参数 ?token=xxx（登录后从页面提取）
"""
import json
import hashlib
import hmac
import requests
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone, timedelta
from time import perf_counter, time
from typing import Any, Dict

from core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "http://libseat.lnu.edu.cn/rest/v2"
_HMAC_SECRET = "leos3cr3t"


def _safe_params(params: dict) -> dict:
    """隐藏 token/cookie 这类敏感参数，便于安全打印。"""
    safe = {}
    for key, value in (params or {}).items():
        lowered = str(key).lower()
        if lowered in ("token", "cookie", "session", "password"):
            text = str(value)
            safe[key] = f"{text[:6]}...{text[-4:]}" if len(text) > 12 else "***"
        else:
            safe[key] = value
    return safe


def _compact_json(value: Any, limit: int = 800) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > limit:
        return text[:limit] + f"... ({len(text)} chars)"
    return text


def _format_time_option(item: dict) -> str:
    value = str(item.get("id", ""))
    if value == "now":
        return "now"
    if value.isdigit():
        mins = int(value)
        return f"{mins // 60:02d}:{mins % 60:02d}"
    return value or str(item)[:40]


def _layout_seat_count(layout: dict) -> int:
    count = 0
    for pos_data in (layout or {}).values():
        if not isinstance(pos_data, dict):
            continue
        if pos_data.get("type") == "empty":
            continue
        if pos_data.get("id") or pos_data.get("seatId"):
            count += 1
    return count


def _response_summary(path: str, payload: dict) -> str:
    if not isinstance(payload, dict):
        return f"payload={type(payload).__name__}"

    status = payload.get("status", "")
    message = payload.get("message") or payload.get("msg") or ""
    data = payload.get("data")
    parts = []
    if status:
        parts.append(f"status={status}")
    if message:
        parts.append(f"message={str(message)[:80]}")

    if isinstance(data, list):
        parts.append(f"data=list[{len(data)}]")
    elif isinstance(data, dict):
        parts.append("data.keys=" + ",".join(list(data.keys())[:8]))
    elif data is not None:
        parts.append(f"data={type(data).__name__}")

    if "/room/stats2/" in path and isinstance(data, list):
        samples = []
        for room in data[:5]:
            if not isinstance(room, dict):
                continue
            name = room.get("room") or room.get("name") or room.get("roomName") or "?"
            rid = room.get("roomId") or room.get("id") or "?"
            free = room.get("free", "?")
            total = room.get("total", "?")
            samples.append(f"{name}(id={rid}, free={free}/{total})")
        if samples:
            parts.append("rooms=" + "; ".join(samples))
    elif "/room/layoutByDate/" in path and isinstance(data, dict):
        layout = data.get("layout", {})
        parts.append(f"layout_seats={_layout_seat_count(layout)}")
    elif "/startTimesForSeat/" in path and isinstance(data, dict):
        starts = data.get("startTimes", [])
        sample = ", ".join(_format_time_option(item) for item in starts[:6] if isinstance(item, dict))
        parts.append(f"startTimes={len(starts)}[{sample}]")
    elif "/endTimesForSeat/" in path and isinstance(data, dict):
        ends = data.get("endTimes", [])
        sample = ", ".join(_format_time_option(item) for item in ends[:6] if isinstance(item, dict))
        parts.append(f"endTimes={len(ends)}[{sample}]")

    return " | ".join(parts) if parts else "no summary"


def _is_seat_time_path(path: str) -> bool:
    return "/startTimesForSeat/" in path or "/endTimesForSeat/" in path


def _short_error(text: str) -> str:
    text = (text or "未知原因").strip()
    return text[:60]


def _sample_available(results: list, limit: int = 5) -> str:
    samples = []
    for item in results[:limit]:
        starts = ",".join(item.get("start_times", [])[:2])
        ends = ",".join(item.get("end_times", [])[-2:])
        samples.append(f"{item.get('seat_num')}({starts}->{ends})")
    return "; ".join(samples)


def _signed_headers(token: str, method: str) -> dict:
    request_id = str(uuid.uuid4())
    request_date = int(time() * 1000)
    raw = f"seat::{request_id}::{request_date}::{method.upper()}"
    request_key = hmac.new(_HMAC_SECRET.encode("utf-8"),
                           raw.encode("utf-8"),
                           hashlib.sha256).hexdigest()
    return {
        "Authorization": token or "",
        "loginType": "PC",
        "X-request-id": request_id,
        "X-request-date": str(request_date),
        "X-hmac-request-key": request_key,
    }


def _bj_date() -> str:
    """返回北京时间日期字符串 YYYY-MM-DD"""
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    return now.strftime("%Y-%m-%d")


def _time_to_minutes(t: str) -> int:
    """HH:MM → 分钟数"""
    parts = t.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def extract_token(driver) -> str:
    """从已登录的页面提取 API token"""
    js_code = """
    // 尝试多种方式提取 token
    let token = '';
    function pickStorageToken(storage) {
        const preferredKeys = [
            'token', 'libseat-m-token', 'accessToken', 'access_token',
            'authToken', 'authorization', 'Authorization'
        ];
        for (const key of preferredKeys) {
            try {
                const value = storage.getItem(key);
                if (value) return value;
            } catch(e) {}
        }
        try {
            for (let i = 0; i < storage.length; i++) {
                const key = storage.key(i) || '';
                if (key.toLowerCase().includes('token')) {
                    const value = storage.getItem(key);
                    if (value) return value;
                }
            }
        } catch(e) {}
        return '';
    }
    // 1. localStorage / sessionStorage（新版网页使用 libseat-m-token）
    try { token = pickStorageToken(localStorage); } catch(e) {}
    if (!token) try { token = pickStorageToken(sessionStorage); } catch(e) {}
    // 2. Vuex store
    if (!token) try {
        let app = document.querySelector('#app').__vue__;
        if (app && app.$store) token = app.$store.state.token || app.$store.state?.user?.token || '';
    } catch(e) {}
    // 3. window.__INITIAL_STATE__
    if (!token) try {
        token = window.__INITIAL_STATE__?.token || window.__INITIAL_STATE__?.user?.token || '';
    } catch(e) {}
    return token;
    """
    try:
        token = driver.execute_script(js_code)
        if token:
            logger.info("✅ Token 已提取: %s...", token[:20])
            return token
    except Exception as e:
        logger.warning("⚠️ Token 提取失败: %s", e)

    # 兜底：从页面请求中抓取（网络嗅探器）
    try:
        collector = getattr(driver, "__sniffer_collect", None)
        if collector:
            requests_list = collector()
            for r in requests_list:
                url = r.get("url", "")
                if "token=" in url:
                    # 从 URL 中提取 token 参数
                    import re
                    match = re.search(r'token=([a-f0-9]+)', url)
                    if match:
                        token = match.group(1)
                        logger.info("✅ Token 从网络请求中提取: %s...", token[:20])
                        return token
    except Exception:
        pass

    logger.error("❌ 无法提取 token")
    return ""


class APIClient:
    """libseat REST API 客户端"""

    def __init__(self, token: str, driver=None, base_url: str = BASE_URL):
        self.token = token
        self.driver = driver
        self._browser_lock = threading.Lock()
        self.base_url = base_url
        self.session = requests.Session()
        self.session.trust_env = False  # 避免系统代理干扰校内 HTTP 接口
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
            "Referer": "http://libseat.lnu.edu.cn/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        })
        # 从 Selenium 浏览器复制 Cookies
        if driver:
            self._copy_cookies(driver)

    def _copy_cookies(self, driver):
        """将 Selenium 浏览器的 Cookies 复制到 requests Session"""
        try:
            selenium_cookies = driver.get_cookies()
            for cookie in selenium_cookies:
                self.session.cookies.set(
                    cookie.get("name", ""),
                    cookie.get("value", ""),
                    domain=cookie.get("domain", ""),
                    path=cookie.get("path", "/"),
                )
            logger.info("🍪 已复制 %d 个 Cookies", len(selenium_cookies))
        except Exception as e:
            logger.warning("⚠️ 复制 Cookies 失败: %s", e)

    def _get(self, path: str, params: dict = None) -> dict:
        """发送 GET 请求"""
        params = dict(params or {})
        params["token"] = self.token
        return self._request("GET", path, params=params)

    def _post(self, path: str, data: dict = None) -> dict:
        """发送 POST 请求"""
        params = {"token": self.token}
        return self._request("POST", path, params=params, data=data or {})

    def _request(self, method: str, path: str, params: dict = None, data: dict = None) -> dict:
        """发送请求并输出过滤后的 API 摘要。"""
        url = f"{self.base_url}{path}"
        params = dict(params or {})
        method = method.upper()
        detail_log = logger.debug if _is_seat_time_path(path) else logger.info
        detail_log("🌐 [API] %s %s params=%s", method, path, _safe_params(params))
        headers = _signed_headers(self.token, method)

        started = perf_counter()
        try:
            if method == "GET":
                resp = self.session.get(url, params=params, headers=headers, timeout=10)
            else:
                resp = self.session.post(url, params=params, json=data or {}, headers=headers, timeout=10)

            elapsed_ms = int((perf_counter() - started) * 1000)
            try:
                payload = resp.json()
            except ValueError:
                preview = (resp.text or "").replace("\n", " ")[:300]
                logger.warning(
                    "⚠️ [API] %s %s -> HTTP %d %dms | 非 JSON 响应: %s",
                    method, path, resp.status_code, elapsed_ms, preview,
                )
                return {"status": "error", "message": f"非 JSON 响应: {preview}"}

            summary = _response_summary(path, payload)
            payload_status = str(payload.get("status", "")).lower() if isinstance(payload, dict) else ""
            if not resp.ok or payload_status in ("error", "fail", "failed"):
                message = payload.get("message") if isinstance(payload, dict) else resp.reason
                if self._needs_browser_fallback(payload):
                    browser_payload = self._browser_request(method, path, params=params, data=data)
                    if browser_payload.get("status") != "error":
                        return browser_payload
                logger.warning(
                    "⚠️ [API] %s %s -> HTTP %d %dms | %s",
                    method, path, resp.status_code, elapsed_ms, summary,
                )
                return {"status": "error", "message": str(message or resp.reason), "data": payload}

            detail_log(
                "✅ [API] %s %s -> HTTP %d %dms | %s",
                method, path, resp.status_code, elapsed_ms, summary,
            )
            logger.debug("📦 [API] %s %s body=%s", method, path, _compact_json(payload))
            return payload
        except requests.RequestException as e:
            logger.warning("⚠️ [API] %s %s 请求失败: %s", method, path, e)
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.warning("⚠️ [API] %s %s 异常: %s", method, path, e)
            return {"status": "error", "message": str(e)}

    def _needs_browser_fallback(self, payload: dict) -> bool:
        if not self.driver or not isinstance(payload, dict):
            return False
        message = str(payload.get("message") or "")
        return payload.get("code") == "20" or "app已停用" in message or "小程序" in message

    def _browser_request(self, method: str, path: str, params: dict = None, data: dict = None) -> dict:
        """在已登录浏览器上下文中调用同源 API，绕过服务端对非浏览器请求的拒绝。"""
        url = f"{self.base_url}{path}"
        params = dict(params or {})
        method = method.upper()
        detail_log = logger.debug if _is_seat_time_path(path) else logger.info
        detail_log("🌐 [API/browser] %s %s params=%s", method, path, _safe_params(params))
        signed_headers = _signed_headers(self.token, method)

        js = """
        const done = arguments[arguments.length - 1];
        const method = arguments[0];
        const url = arguments[1];
        const params = arguments[2] || {};
        const data = arguments[3] || {};
        const signedHeaders = arguments[4] || {};
        const query = new URLSearchParams(params).toString();
        const target = url + (query ? (url.includes('?') ? '&' : '?') + query : '');
        const options = {
            method,
            credentials: 'include',
            headers: Object.assign({
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json;charset=UTF-8'
            }, signedHeaders)
        };
        if (method !== 'GET') {
            options.body = JSON.stringify(data || {});
        }
        fetch(target, options)
            .then(async (resp) => done({
                ok: resp.ok,
                status: resp.status,
                text: await resp.text()
            }))
            .catch((err) => done({
                ok: false,
                status: 0,
                error: String(err)
            }));
        """

        with self._browser_lock:
            try:
                self.driver.set_script_timeout(15)
            except Exception:
                pass
            try:
                result = self.driver.execute_async_script(js, method, url, params, data or {}, signed_headers)
            except Exception as exc:
                logger.warning("⚠️ [API/browser] %s %s 调用失败: %s", method, path, exc)
                return {"status": "error", "message": str(exc)}

        if result.get("error"):
            logger.warning("⚠️ [API/browser] %s %s fetch失败: %s", method, path, result["error"])
            return {"status": "error", "message": result["error"]}

        try:
            payload = json.loads(result.get("text") or "{}")
        except ValueError:
            preview = (result.get("text") or "").replace("\n", " ")[:300]
            logger.warning(
                "⚠️ [API/browser] %s %s -> HTTP %s | 非 JSON 响应: %s",
                method, path, result.get("status"), preview,
            )
            return {"status": "error", "message": f"非 JSON 响应: {preview}"}

        summary = _response_summary(path, payload)
        payload_status = str(payload.get("status", "")).lower() if isinstance(payload, dict) else ""
        if not result.get("ok") or payload_status in ("error", "fail", "failed"):
            logger.warning(
                "⚠️ [API/browser] %s %s -> HTTP %s | %s",
                method, path, result.get("status"), summary,
            )
            return {"status": "error", "message": str(payload.get("message", "")), "data": payload}

        detail_log(
            "✅ [API/browser] %s %s -> HTTP %s | %s",
            method, path, result.get("status"), summary,
        )
        logger.debug("📦 [API/browser] %s %s body=%s", method, path, _compact_json(payload))
        return payload

    # ──────────────────────── 高层 API ────────────────────────

    def get_floors(self, building_id: int) -> list:
        """获取校区的楼层列表"""
        resp = self._post(f"/room/floors/{building_id}")
        return resp.get("data", [])

    def get_room_stats(self, building_id: int, date: str = "") -> list:
        """获取校区所有房间的统计信息（含空闲座位数 free）"""
        if not date:
            date = _bj_date()
        resp = self._get(f"/room/stats2/{building_id}/{date}",
                         params={"buildingId": building_id, "date": date})
        return resp.get("data", [])

    def get_room_layout(self, room_id: int, date: str = "") -> dict:
        """获取房间座位布局，含所有座位ID"""
        if not date:
            date = _bj_date()
        resp = self._get(f"/room/layoutByDate/{room_id}/{date}",
                         params={"id": room_id, "date": date})
        return resp.get("data", {})

    def get_start_times(self, seat_id: int, date: str = "") -> dict:
        """获取座位的可用开始时间"""
        if not date:
            date = _bj_date()
        resp = self._get(f"/startTimesForSeat/{seat_id}/{date}",
                         params={"seatId": seat_id, "date": date})
        return resp

    def get_end_times(self, seat_id: int, date: str = "", start: str = "") -> dict:
        """获取座位的可用结束时间（基于选定的开始时间）"""
        if not date:
            date = _bj_date()
        resp = self._get(f"/endTimesForSeat/{seat_id}/{date}/{start}",
                         params={"id": seat_id, "date": date, "start": start})
        return resp

    def get_seat_availability(self, seat_id: int, date: str = "") -> dict:
        """一站式获取单个座位的完整可用时间信息"""
        result = {"seat_id": str(seat_id), "available": False,
                  "start_times": [], "end_times": [], "error": ""}

        # 获取开始时间
        start_resp = self.get_start_times(seat_id, date)
        if start_resp.get("status") != "success":
            result["error"] = f"获取开始时间失败: {start_resp.get('message','')}"
            return result

        start_data = start_resp.get("data", {})
        starts_raw = start_data.get("startTimes", [])

        if not starts_raw:
            result["error"] = "无可用开始时间"
            return result

        # 解析开始时间
        starts = []
        for s in starts_raw:
            sid = s.get("id", "")
            if sid == "now":
                # "现在" → 当前北京时间
                now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
                starts.append(now.strftime("%H:%M"))
            elif sid.isdigit():
                mins = int(sid)
                starts.append(f"{mins // 60:02d}:{mins % 60:02d}")

        if not starts:
            result["error"] = "开始时间为空"
            return result

        result["start_times"] = starts

        # 获取结束时间（基于最早可用开始时间）
        best_start = starts[0]
        start_param = start_data.get("startTimes", [{}])[0].get("id", best_start)
        end_resp = self.get_end_times(seat_id, date, start_param)
        if end_resp.get("status") != "success":
            result["error"] = f"获取结束时间失败: {end_resp.get('message','')}"
            return result

        ends_data = end_resp.get("data", {}).get("endTimes", [])
        ends = []
        for e in ends_data:
            eid = str(e.get("id", ""))
            if eid.isdigit():
                mins = int(eid)
                ends.append(f"{mins // 60:02d}:{mins % 60:02d}")

        if not ends:
            result["error"] = "结束时间为空"
            return result

        result["end_times"] = ends
        result["available"] = True
        return result

    def scan_room_api(self, room_id: int, room_name: str, date: str = "",
                      prefer_seats: list = None) -> list:
        """通过 API 扫描整个房间的所有座位可用时间。

        流程：
          1. 获取房间布局 → 提取所有座位ID
          2. 并发获取每个座位的开始/结束时间
          3. 过滤并排序结果

        Args:
            room_id: 房间ID（从 room/stats2 获取）
            room_name: 房间名称
            date: 日期 YYYY-MM-DD
            prefer_seats: 优先座位号列表（可选）

        Returns:
            [{"seat_num": "92", "room_name": "...", "available": True,
              "start_times": [...], "end_times": [...]}, ...]
        """
        import concurrent.futures

        logger.info("🚀 [API] 扫描房间 %s (ID=%d)...", room_name, room_id)

        # 1. 获取布局
        layout_data = self.get_room_layout(room_id, date)
        if not layout_data:
            logger.error("❌ [API] 无法获取房间 %s 布局", room_name)
            return []

        layout = layout_data.get("layout", {})
        # 从 layout 中提取所有座位ID（type != "empty" 的条目）
        seat_labels = {}
        for pos_key, pos_data in layout.items():
            if not isinstance(pos_data, dict):
                continue
            if pos_data.get("type") == "empty":
                continue
            sid = pos_data.get("id") or pos_data.get("seatId")
            if sid:
                seat_id = int(sid)
                seat_label = (
                    pos_data.get("name")
                    or pos_data.get("seatName")
                    or pos_data.get("label")
                    or str(seat_id)
                )
                seat_labels[seat_id] = str(seat_label)

        seat_ids = set(seat_labels)

        if not seat_ids:
            logger.warning("⚠️ [API] 房间 %s 布局中未找到座位", room_name)
            return []

        logger.info("📊 [API] 房间 %s 共 %d 个座位，开始API扫描...", room_name, len(seat_ids))

        # 2. 优先座位先扫
        prefer_set = set()
        if prefer_seats:
            prefer_set = {int(s) for s in prefer_seats if str(s).isdigit()}

        preferred_ids = [s for s in seat_ids if s in prefer_set]
        normal_ids = [s for s in seat_ids if s not in prefer_set]

        results = []
        errors = Counter()

        def collect_result(info):
            if not info:
                errors["无返回"] += 1
                return
            if info.get("available"):
                seat_id = int(info.get("seat_id") or info.get("seat_num"))
                info["seat_id"] = str(seat_id)
                info["seat_num"] = seat_labels.get(seat_id, str(seat_id))
                info["room_name"] = room_name
                results.append(info)
            else:
                errors[_short_error(info.get("error"))] += 1

        def scan_one(seat_id):
            try:
                info = self.get_seat_availability(seat_id, date)
                info["seat_id"] = str(seat_id)
                return info
            except Exception as e:
                logger.debug("[API] 座位 %d 扫描异常: %s", seat_id, e)
                return {"seat_id": str(seat_id), "available": False,
                        "error": f"扫描异常: {type(e).__name__}"}

        # 优先座位先扫描
        for sid in preferred_ids:
            r = scan_one(sid)
            collect_result(r)
            if r and r.get("available"):
                logger.info("★ [API] 优先座位 %d 可用: %s", sid, r["end_times"])

        # 再扫其余座位
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(scan_one, sid): sid for sid in normal_ids}
            for future in concurrent.futures.as_completed(futures):
                collect_result(future.result())

        logger.info("✅ [API] %s 扫描完成: %d/%d 可用",
                     room_name, len(results), len(seat_ids))
        if results:
            logger.info("📌 [API] %s 可用样例: %s", room_name, _sample_available(results))
        if errors:
            error_summary = "; ".join(f"{reason}={count}" for reason, count in errors.most_common(5))
            logger.info("ℹ️ [API] %s 不可用/失败原因: %s", room_name, error_summary)
        return results


# ──────────────────────── 全局便捷函数 ────────────────────────

_client_cache: Dict[str, APIClient] = {}


def get_client(token: str, driver=None) -> APIClient:
    """获取或创建 API 客户端（缓存）。driver 用于复制 Cookies。"""
    if token not in _client_cache:
        _client_cache[token] = APIClient(token, driver=driver)
    elif driver:
        _client_cache[token].driver = driver
        if not _client_cache[token].session.cookies:
            _client_cache[token]._copy_cookies(driver)
    return _client_cache[token]
