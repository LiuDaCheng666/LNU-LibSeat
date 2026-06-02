"""LibSeat Allocator — 现代磨砂玻璃主题（亮色 + 暗色双主题）

Qt 对 CSS rgba() 支持不稳定，全部使用预计算的实色 hex。
磨砂效果通过微渐变 + 多层阴影模拟，层次感更强。

自动检测操作系统主题，并允许用户手动切换。
"""
import ctypes
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QGraphicsDropShadowEffect


# ═══════════════════════════════════
#  操作系统主题检测
# ═══════════════════════════════════

def _is_windows_dark():
    """通过注册表读取 Windows 是否使用暗色模式"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except Exception:
        return False


def _is_macos_dark():
    """通过 defaults 读取 macOS 是否使用暗色模式"""
    if sys.platform != "darwin":
        return False
    try:
        import subprocess
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip().lower() == "dark"
    except Exception:
        return False


def detect_os_theme():
    """返回操作系统当前主题: 'dark' 或 'light'"""
    if _is_windows_dark() or _is_macos_dark():
        return "dark"
    return "light"


# ═══════════════════════════════════
#  亮色主题色板
# ═══════════════════════════════════

LIGHT_THEME = {
    "BG":              "#ebeaf0",
    "BG_TOP":          "#eeedf3",   # 全局背景渐变 — 微暖
    "BG_BOTTOM":       "#e8e7ed",   # 全局背景渐变 — 微冷
    "GRAY_50":         "#faf9fc",
    "GRAY_100":        "#f5f4f8",
    "GRAY_200":        "#f0eef4",
    "GRAY_300":        "#e8e6ec",
    "GRAY_400":        "#dcdae2",
    "GRAY_500":        "#c8c6ce",
    "CARD":            "#f5f4f8",
    "CARD_HOVER":      "#faf9fc",
    "CARD_ACCENT":     "#f0eef4",
    "INPUT":           "#ffffff",
    "INPUT_HOVER":     "#fdfdfe",
    "BAR_BG":          "#f3f2f6",
    "TERM_BG":         "#1a1a2e",
    "TERM_HEADER":     "#222236",
    "TERM_TEXT":       "#d4d4d4",
    "TERM_ACCENT":     "#569cd6",
    "TERM_GREEN":      "#6a9955",
    "TERM_YELLOW":     "#dcdcaa",
    "TERM_RED":        "#f44747",
    "TERM_CYAN":       "#4ec9b0",
    "TERM_BORDER":     "#333348",
    "TERM_LINE_NUM":   "#555568",
    "NESTED_BG":       "#e8e6ec",
    "BORDER":          "#dcdae2",
    "BORDER_LIGHT":    "#e4e2e8",
    "BORDER_FOCUS":    "#5b8def",
    "BORDER_ACCENT":   "#8aadf4",
    "ACCENT":          "#4a7cf7",
    "ACCENT_HOT":      "#3b6de6",
    "ACCENT_SOFT":     "#e8f0fe",
    "PURPLE":          "#6c5ce7",
    "PURPLE_HOT":      "#5b4bd6",
    "GRADIENT_BLUE_START":  "#5b8def",
    "GRADIENT_BLUE_END":    "#4a7cf7",
    "GRADIENT_PURPLE_START": "#7c6ef0",
    "GRADIENT_PURPLE_END":   "#6c5ce7",
    "SUCCESS":         "#2ecc71",
    "SUCCESS_SOFT":    "#e6f9f0",
    "WARN":            "#f39c12",
    "WARN_SOFT":       "#fef8e8",
    "ERR":             "#e74c3c",
    "ERR_SOFT":        "#fdeaea",
    "TEXT":            "#1e1e2a",
    "TEXT_SEC":        "#3d3d4a",
    "TEXT_MUTED":      "#6e6e7c",
    "TEXT_DIM":        "#aaaab6",
    "TEXT_INVERT":     "#ffffff",
    "SHADOW_BG":       "#000000",
    "SHADOW_BLUE":     "#4a7cf7",
    # 嵌套框底色（淡蓝色调，区别于卡片灰色）
    "FRAMED_BG":       "#ecf1fa",
}


# ═══════════════════════════════════
#  暗色主题色板
# ═══════════════════════════════════

DARK_THEME = {
    "BG":              "#1a1a28",
    "BG_TOP":          "#1c1c2c",   # 全局背景渐变 — 微亮
    "BG_BOTTOM":       "#181824",   # 全局背景渐变 — 微深
    "GRAY_50":         "#252538",
    "GRAY_100":        "#2a2a40",
    "GRAY_200":        "#30304a",
    "GRAY_300":        "#383858",
    "GRAY_400":        "#484870",
    "GRAY_500":        "#5a5a82",
    "CARD":            "#2a2a40",
    "CARD_HOVER":      "#252538",
    "CARD_ACCENT":     "#30304a",
    "INPUT":           "#2a2a40",
    "INPUT_HOVER":     "#32324a",
    "BAR_BG":          "#222238",
    "TERM_BG":         "#0f0f1a",
    "TERM_HEADER":     "#181828",
    "TERM_TEXT":       "#d4d4d4",
    "TERM_ACCENT":     "#569cd6",
    "TERM_GREEN":      "#6a9955",
    "TERM_YELLOW":     "#dcdcaa",
    "TERM_RED":        "#f44747",
    "TERM_CYAN":       "#4ec9b0",
    "TERM_BORDER":     "#2a2a45",
    "TERM_LINE_NUM":   "#4a4a68",
    "NESTED_BG":       "#222238",
    "BORDER":          "#484870",
    "BORDER_LIGHT":    "#3a3a58",
    "BORDER_FOCUS":    "#6b9dff",
    "BORDER_ACCENT":   "#5a7de0",
    "ACCENT":          "#5b8df0",
    "ACCENT_HOT":      "#4a7ce6",
    "ACCENT_SOFT":     "#1e2a48",
    "PURPLE":          "#7b6cf0",
    "PURPLE_HOT":      "#6a5be0",
    "GRADIENT_BLUE_START":  "#6b9dff",
    "GRADIENT_BLUE_END":    "#5b8df0",
    "GRADIENT_PURPLE_START": "#8b7cf8",
    "GRADIENT_PURPLE_END":   "#7b6cf0",
    "SUCCESS":         "#2ecc71",
    "SUCCESS_SOFT":    "#1a3a2a",
    "WARN":            "#f0a020",
    "WARN_SOFT":       "#3a2e10",
    "ERR":             "#e74c3c",
    "ERR_SOFT":        "#3a1a1a",
    "TEXT":            "#d8d8e8",
    "TEXT_SEC":        "#c0c0d0",
    "TEXT_MUTED":      "#9090a8",
    "TEXT_DIM":        "#6a6a80",
    "TEXT_INVERT":     "#1a1a28",
    "SHADOW_BG":       "#000000",
    "SHADOW_BLUE":     "#5b8df0",
    # 嵌套框底色（暗蓝色调，区别于卡片深灰色）
    "FRAMED_BG":       "#1c2438",
}


# ═══════════════════════════════════
#  C 类 — 当前主题色（运行时可变）
# ═══════════════════════════════════

class _ThemeColors:
    """持有当前主题的所有颜色。通过 C 单例访问。"""

    def __init__(self):
        self._apply(LIGHT_THEME)

    def _apply(self, palette: dict):
        for key, value in palette.items():
            setattr(self, key, value)

    def apply_light(self):
        self._apply(LIGHT_THEME)

    def apply_dark(self):
        self._apply(DARK_THEME)


C = _ThemeColors()

# 当前主题名
_current_theme_name = "light"

# 主题变更回调列表
_theme_callbacks = []


def current_theme():
    """返回当前主题名称: 'light' 或 'dark'"""
    return _current_theme_name


def on_theme_changed(callback):
    """注册主题变更回调。callback 接收 ('light'|'dark') 参数。"""
    _theme_callbacks.append(callback)


def set_theme(name: str):
    """切换主题并触发所有回调。"""
    global _current_theme_name
    if name == _current_theme_name:
        return
    if name == "dark":
        C.apply_dark()
    else:
        C.apply_light()
    _current_theme_name = name
    for cb in _theme_callbacks:
        try:
            cb(name)
        except Exception:
            pass


def toggle_theme():
    """在亮色/暗色之间切换"""
    set_theme("dark" if _current_theme_name == "light" else "light")


# ═══════════════════════════════════
#  字体
# ═══════════════════════════════════

FONT_FAMILY = ["Segoe UI", "Microsoft YaHei UI", "PingFang SC", "sans-serif"]
MONO_FAMILY = ["Cascadia Code", "JetBrains Mono", "Consolas", "monospace"]

# 圆角阶梯（不随主题变化）
RADIUS_XS  = 4
RADIUS_SM  = 6
RADIUS_MD  = 8
RADIUS_LG  = 10
RADIUS_XL  = 12
RADIUS_2XL = 14


def _font(families, size, bold=False):
    f = QFont()
    f.setFamilies(families)
    f.setPointSize(size)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


def sans(size, bold=False):
    return _font(FONT_FAMILY, size, bold)


def mono(size, bold=False):
    return _font(MONO_FAMILY, size, bold)


# ═══════════════════════════════════
#  阴影效果（模拟磨砂层次）
# ═══════════════════════════════════

def _make_shadow(widget, blur, offset_x, offset_y, color_hex, alpha):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(offset_x, offset_y)
    qc = QColor(color_hex)
    qc.setAlpha(alpha)
    eff.setColor(qc)
    return eff


def frosted_shadow(widget):
    """磨砂卡片阴影：大面积柔光 + 微偏移"""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(32)
    eff.setOffset(0, 6)
    qc = QColor(C.SHADOW_BG)
    qc.setAlpha(22)
    eff.setColor(qc)
    return eff


def card_shadow(widget):
    """紧凑卡片阴影：适合小卡片"""
    return _make_shadow(widget, 16, 0, 4, C.SHADOW_BG, 18)


def soft_glow(widget, color=None, blur=14, alpha=25):
    """柔光效果 — 用于按钮等"""
    return _make_shadow(widget, blur, 0, 0, color or C.ACCENT, alpha)


def elevated_shadow(widget):
    """悬浮阴影 — 模拟 elevation=8"""
    return _make_shadow(widget, 24, 0, 8, C.SHADOW_BG, 28)


# ═══════════════════════════════════
#  公共样式片段（函数形式，每次调用
#  基于当前 C 值生成，支持主题切换）
# ═══════════════════════════════════

# 磨砂卡片
def card_style():
    return f"""
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {C.GRAY_50},
            stop:1 {C.GRAY_100});
        border: 1px solid {C.BORDER_LIGHT};
        border-radius: {RADIUS_2XL}px;
    """

# 次级卡片
def card_sub_style():
    return f"""
        background: {C.GRAY_200};
        border: 1px solid {C.BORDER_LIGHT};
        border-radius: {RADIUS_LG}px;
    """

# 输入框
def input_style():
    return f"""
        background: {C.INPUT};
        border: 1px solid {C.BORDER};
        border-radius: {RADIUS_MD}px;
        padding: 0 12px;
        color: {C.TEXT};
    """

def input_focus():
    return f"border: 1.5px solid {C.BORDER_FOCUS}; background: {C.INPUT_HOVER};"

# 下拉框
def combo_style():
    return f"""
        background: {C.INPUT};
        border: 1px solid {C.BORDER};
        border-radius: {RADIUS_MD}px;
        padding: 0 10px;
        color: {C.TEXT};
    """

def combo_focus():
    return f"border: 1.5px solid {C.BORDER_FOCUS};"

def combo_popup():
    return f"""
        background: {C.INPUT};
        color: {C.TEXT};
        border: 1px solid {C.BORDER};
        border-radius: {RADIUS_MD}px;
        padding: 4px;
        selection-background-color: {C.ACCENT_SOFT};
        selection-color: {C.TEXT};
    """

# 滚动条
def scrollbar_style():
    return "background: transparent; width: 5px;"

def scrollbar_handle():
    return f"""
        background: {C.GRAY_400};
        border-radius: 3px;
        min-height: 24px;
    """

def scrollbar_hover():
    return f"background: {C.ACCENT}; border-radius: 3px;"


# ═══════════════════════════════════
#  向后兼容别名（模块级，导入时立即
#  求值，主题切换后不会自动更新 —
#  建议新代码使用函数形式）
# ═══════════════════════════════════

# 这些保留作为旧代码的兼容层；由于它们是在导入时用 f-string
# 求值的，主题切换后不会自动变化。ConfigPanel 等核心组件
# 已迁移到使用函数形式。
COMBO_STYLE     = combo_style()
COMBO_POPUP     = combo_popup()
SCROLLBAR_STYLE = scrollbar_style()
SCROLLBAR_HANDLE = scrollbar_handle()
SCROLLBAR_HOVER = scrollbar_hover()
CARD_STYLE      = card_style()
CARD_SUB_STYLE  = card_sub_style()
INPUT_STYLE     = input_style()
INPUT_FOCUS     = input_focus()
COMBO_FOCUS     = combo_focus()
