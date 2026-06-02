"""CDP 网络嗅探器 — 自动捕获页面API请求，发现座位数据接口。

使用 Chrome DevTools Protocol 监听 XHR/Fetch 请求，
记录所有 API URL 和响应内容，帮助发现座位可用时间的后端接口。
"""
import json
import time
import threading
from typing import Callable, Optional

from core.logger import get_logger

logger = get_logger(__name__)

# 哪些请求值得记录（过滤掉静态资源）
_API_PATH_KEYWORDS = [
    "api", "seat", "room", "reserve", "booking", "time",
    "schedule", "available", "library", "campus", "area",
    "space", "resource", "grid", "list", "query", "search",
]


class NetworkSniffer:
    """基于 CDP 的网络请求监听器"""

    def __init__(self, driver, account: str = ""):
        self.driver = driver
        self.account = account
        self._enabled = False
        self._requests = []  # 存储捕获的请求信息
        self._response_bodies = {}  # requestId -> body
        self._listener_thread = None
        self._stop_event = threading.Event()

    @property
    def captured_requests(self):
        return list(self._requests)

    def start(self):
        """启用网络监听"""
        if self._enabled:
            return

        try:
            # 启用 Network 域
            self.driver.execute_cdp_cmd("Network.enable", {})
            self._enabled = True
            logger.info("🔍 [%s] CDP 网络嗅探已启用", self.account)
        except Exception as e:
            logger.warning("⚠️ [%s] CDP Network.enable 失败: %s", self.account, e)

    def stop(self) -> list:
        """停止监听，返回所有捕获的 API 请求"""
        self._enabled = False
        return self.captured_requests

    def poll_responses(self):
        """轮询一次：获取所有已接收但未读的响应。

        在关键操作后调用（如进入房间、点击座位），收集这段时间内的 API 请求。
        """
        if not self._enabled:
            return

        try:
            # CDP 没有直接的"获取所有待处理事件"API，
            # 但我们可以通过检查最近的请求来收集
            pass
        except Exception:
            pass

    def capture_request(self, request_id: str, url: str, method: str,
                        status: int, response_body: str = ""):
        """记录一个 API 请求"""
        # 过滤静态资源
        if any(ext in url.lower() for ext in [".js", ".css", ".png", ".jpg",
                                               ".jpeg", ".gif", ".svg", ".ico",
                                               ".woff", ".ttf", ".woff2", ".map"]):
            return

        # 只记录可能的 API 请求
        is_api = any(kw in url.lower() for kw in _API_PATH_KEYWORDS)

        record = {
            "url": url,
            "method": method,
            "status": status,
            "is_api": is_api,
            "body_preview": response_body[:2000] if response_body else "",
            "timestamp": time.time(),
        }
        self._requests.append(record)

        if is_api:
            logger.info("🌐 [%s] API: %s %s → %d (body:%d chars)",
                        self.account, method, url, status,
                        len(response_body) if response_body else 0)
            # 对座位相关的 API 详细记录
            if any(kw in url.lower() for kw in ["seat", "room", "available", "time", "grid"]):
                preview = (response_body or "")[:500]
                logger.info("📦 [%s] Response preview: %s", self.account, preview)


def capture_api_requests(driver, account: str = "") -> list:
    """一次性方法：启用 CDP，执行一段 JS 来劫持 fetch/XHR 并收集请求。

    这个方法不依赖持续的 CDP 事件监听，而是注入 JS 拦截器，
    然后返回在页面操作期间收集到的请求列表。
    适用于快速嗅探。
    """
    requests = []

    js_sniffer = """
    // 劫持 fetch
    const _origFetch = window.fetch;
    window.__capturedRequests = [];
    window.fetch = function(...args) {
        const start = Date.now();
        return _origFetch.apply(this, args).then(async (resp) => {
            const clone = resp.clone();
            let body = '';
            try { body = await clone.text(); } catch(e) {}
            window.__capturedRequests.push({
                url: args[0]?.url || String(args[0]),
                method: args[0]?.method || (args[1]?.method || 'GET'),
                status: resp.status,
                body: body.substring(0, 3000),
                time: start
            });
            return resp;
        });
    };
    // 劫持 XMLHttpRequest
    const _origOpen = XMLHttpRequest.prototype.open;
    const _origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
        this.__url = url;
        this.__method = method;
        return _origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(body) {
        this.addEventListener('load', function() {
            window.__capturedRequests.push({
                url: this.__url,
                method: this.__method,
                status: this.status,
                body: (this.responseText || '').substring(0, 3000),
                time: Date.now()
            });
        });
        return _origSend.apply(this, arguments);
    };
    return 'sniffer_installed';
    """

    try:
        result = driver.execute_script(js_sniffer)
        logger.info("🔍 [%s] JS 网络嗅探器注入: %s", account, result)
    except Exception as e:
        logger.warning("⚠️ [%s] JS 嗅探器注入失败: %s", account, e)
        return requests

    # 返回一个闭包函数来收集结果
    def collect():
        try:
            raw = driver.execute_script("return JSON.stringify(window.__capturedRequests || []);")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return []

    # 存储 collector 以便后续调用
    driver.__sniffer_collect = collect
    return collect


def collect_sniffer_results(driver) -> list:
    """收集注入的 JS 嗅探器结果"""
    collector = getattr(driver, "__sniffer_collect", None)
    if collector:
        try:
            results = collector()
            return results
        except Exception:
            pass
    return []
