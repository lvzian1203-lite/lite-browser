"""手工维护的界面翻译（与自动生成的 catalog_en 分离，避免被重新生成覆盖）。

放这里的内容有两类：

1. 内置页面（错误页 / 可疑网址提示页）里的整句文案 —— 它们是长 HTML 模板的一部分，
   不适合整体自动包装，由 ``i18n.tr_html`` 做短语替换；
2. 主题名称等少量固定文案。
"""

from __future__ import annotations

EXTRA: dict[str, str] = {
    # ---- 错误页（猫追鼠标）----
    "重新加载": "Reload",
    "返回上一页": "Go back",
    "回到主页": "Home page",
    "动一动鼠标，让小猫帮你把页面追回来 🐾":
        "Move the mouse — the cat will chase the page back for you 🐾",
    "该页面打不开": "This page can't be opened",
    # ---- 可疑网址提示页 ----
    "已暂停打开该网址。请确认您信任该网站后再继续。":
        "Opening this URL is paused. Continue only if you trust this website.",
    "我了解风险，继续访问": "I understand the risk — continue",
    "提示：可在「设置 → 隐私与安全 → 可疑网址拦截」中管理黑名单与规则。":
        "Tip: manage the block list and rules in "
        "Settings → Privacy and security → Suspicious URL blocking.",
    "该网址命中本地可疑规则": "This URL matched a local suspicious-URL rule",
    # ---- 主题名称 ----
    "Windows 98 / 2000 经典": "Windows 98 / 2000 Classic",
    "Windows 7 (Aero)": "Windows 7 (Aero)",
    "HarmonyOS（鸿蒙）": "HarmonyOS",
    "哈基米（猫猫）": "Hakimi (Cat)",
    # ---- 默认书签标题 ----
    "必应搜索": "Bing Search",
    "百度": "Baidu",
    # ---- 内核名称（帮助表格与设置页）----
    "Edge WebView2（Chromium，含 H.264/AAC）": "Edge WebView2 (Chromium, with H.264/AAC)",
    "QtWebEngine（Chromium，仅开源编解码器）": "QtWebEngine (Chromium, open codecs only)",
    "自动选择": "Automatic",
    # ---- 帮助正文里「标签 + 动态值」混排的片段 ----
    '一款用 Python 编写的轻量浏览器，界面为仿 Windows 经典风格，作者': 'A lightweight browser written in Python with a classic Windows look. Author',
    '。': '.',
    ' 种 UI 风格': ' UI styles',
    '：「设置 → 外观 → 界面风格」，': ': "Settings → Appearance → UI style",',
    '切换立即生效，无需重启。': 'Changes take effect immediately; no restart needed.',
    '程序内置两种 Chromium 内核，启动时自动选择，也可在': 'Two Chromium engines are bundled; the browser picks one automatically at startup, or you can force one in',
    '「设置 → 外观 → 渲染引擎」强制指定（切换后需重启程序）。': '"Settings → Appearance → Rendering engine" (restart required after switching).',
    '（Ruffle 0.6.0，Rust 编写的 Flash 运行时，编译成 WebAssembly），': '(Ruffle 0.6.0, a Flash runtime written in Rust and compiled to WebAssembly),',
    '名称：': 'Name: ',
    '版本：': 'Version: ',
    '作者：': 'Author: ',
    '版权：': 'License: ',

    # ---- 其它固定文案 ----
    "中文（简体）": "Chinese (Simplified)",
    "界面语言已切换为 {0}。\n菜单与对话框将在重新启动程序后全部生效。":
        "The interface language is now {0}.\n"
        "Menus and dialogs will fully switch after you restart the browser.",
    "切换到 English 后，菜单、对话框与提示都会变成英文":
        "Switch to English for menus, dialogs and messages",
    "界面语言(L)：": "Language (L): ",
}
