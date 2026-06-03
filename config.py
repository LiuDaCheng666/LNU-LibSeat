# ===================================================================
# LibSeat Allocator 配置文件
# ===================================================================

# ── 账号 ──
USERS = {
    "": {
        "password": "",
    },
}

# ── 目标 ──
TARGET_CAMPUS = "崇山校区图书馆"
TARGET_ROOM = "三楼智慧研修空间"

# ── 全天时间段 ──
ALLOC_DAY_START = "09:00"
ALLOC_DAY_END = "21:00"

# ── 模式: "multi" = 多账号分时段 | "single" = 单账号逐段 ──
ALLOCATION_MODE = "multi"

# ── 测试模式: 只抓取 API 空闲座位并生成方案，不执行预约 ──
ALLOC_DRY_RUN = False

# ── 多账号模式: 最多账号数 (1-3) ──
ALLOC_MAX_ACCOUNTS = 3

# ── 跨房间搜索 ──
ALLOC_CROSS_ROOM = True
ALLOC_CROSS_ROOMS = []

# ── 单账号模式: 提前多少分钟查找下一座位 ──
ALLOC_PRE_NOTIFY_MINUTES = 30

# ── 单账号模式: 自动取消并换座（无需确认）──
ALLOC_AUTO_CANCEL = False

# ── 通知超时（秒）──
ALLOC_NOTIFY_TIMEOUT = 300

# ── 邮箱通知 ──
RECEIVER_EMAIL = ""
SMTP_USER = "lnu_library@163.com"
SMTP_PASS = "LWQWA366dd2g6msK"

# ── 浏览器: "edge" | "chrome" ──
BROWSER = "edge"
DRIVER_PATH = ""
WEBDRIVER_CACHE = ""

# ── 日志 ──
LOG_LEVEL = "INFO"
GUI_LOG_LEVEL = "INFO"  # GUI 输出过滤级别，可改为 "DEBUG" 查看更细日志
LOG_DIR = "logs"
