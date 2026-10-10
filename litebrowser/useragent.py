"""User-Agent 预设与处理。

「设置 → 网络」里可以选择预设，也可以完全自定义，
清空自定义内容即恢复内核默认 UA。
"""

from __future__ import annotations

from .i18n import tr, trf

#: 预设 UA（名称, 值）；值为空字符串表示使用内核默认
UA_PRESETS: list[tuple[str, str]] = [
    (tr("默认（跟随内核）"), ""),
    (
        "Windows · Chrome 131",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ),
    (
        "Windows · Edge 131",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    ),
    (
        "Windows · Firefox 133",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    ),
    (
        "macOS · Safari 18",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    ),
    (
        "Linux · Chrome 131",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ),
    (
        tr("Android · 手机版"),
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    ),
    (
        tr("iPhone · 手机版"),
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    ),
    (
        tr("iPad · 平板版"),
        "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    ),
    (
        tr("微信内置浏览器"),
        "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 "
        "MicroMessenger/8.0.49.2600(0x2800313D) WeChat/arm64",
    ),
    (tr("自定义（在下方输入）"), "__custom__"),
]

#: 移动端特征，用于给界面一些提示
MOBILE_MARKERS = ("Mobile", "Android", "iPhone", "iPad", "MicroMessenger")


def default_user_agent() -> str:
    """当前内核的默认 UA（延迟导入，避免循环依赖）。"""
    try:
        from .qtengine import qt_default_user_agent

        return qt_default_user_agent()
    except Exception:
        return ""


def is_mobile(user_agent: str) -> bool:
    return any(marker in (user_agent or "") for marker in MOBILE_MARKERS)


def preset_index(user_agent: str) -> int:
    """返回与给定 UA 匹配的预设下标；不匹配则返回「自定义」。"""
    value = (user_agent or "").strip()
    for index, (_name, preset) in enumerate(UA_PRESETS):
        if preset and preset == value:
            return index
    if not value:
        return 0
    return len(UA_PRESETS) - 1


def resolve(user_agent: str) -> str:
    """把配置值解析成最终要设置的 UA。"""
    value = (user_agent or "").strip()
    if value == "__custom__":
        return ""
    return value
