"""使用帮助：每项功能的作用与解释。

为了保证「随功能变动更新」，帮助里的**可变部分全部从程序本身读取**：

* 快捷键一览 —— 扫描主窗口里所有带快捷键的 QAction；
* 界面风格 —— 读取 ``theme.theme_names()``；
* 渲染引擎 —— 读取 ``engine.ENGINE_LABELS`` 与当前内核能力；
* 搜索引擎 / User-Agent 预设 —— 读取配置与 ``useragent.UA_PRESETS``。

功能本身的文字说明集中在 :data:`SECTIONS`，随版本维护。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .config import APP_NAME, APP_VERSION, AUTHOR, COPYRIGHT, SEARCH_ENGINES
from .videocheck import BILI_VIDEO
from .widgets import XPDialog

from .i18n import tr, trf, tr_text


def _ruffle_text() -> str:
    """从实际文件读取 Ruffle 版本（打包后也能正确显示）。"""
    try:
        from .ruffle import version_text

        return version_text()
    except Exception:
        return "Ruffle"


@dataclass
class Topic:
    """一个帮助主题。"""

    key: str
    title: str
    body: str
    icon: str = "info"
    children: list["Topic"] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 动态内容
# --------------------------------------------------------------------------- #
def _shortcuts_table(window=None) -> str:
    """从主窗口收集所有快捷键（功能增删后自动同步）。"""
    rows: list[tuple[str, str]] = []
    if window is not None:
        seen: set[str] = set()
        for action in getattr(window, "_shortcut_actions", []):
            try:
                text = action.text().replace("&", "").strip()
                sequence = action.shortcut().toString()
            except Exception:
                continue
            if not sequence or sequence in seen:
                continue
            seen.add(sequence)
            rows.append((sequence, text))

    if not rows:
        rows = [
            ("Ctrl+T", tr("新建标签页")),
            ("Ctrl+W", tr("关闭标签页")),
            ("Ctrl+L", tr("定位地址栏")),
            ("Ctrl+F", tr("页面内查找")),
        ]

    lines = [
        "<table cellspacing='0' cellpadding='4' width='100%'>",
        tr("<tr><th align='left'>快捷键</th><th align='left'>功能</th></tr>"),
    ]
    for sequence, text in rows:
        lines.append(
            f"<tr><td><code>{sequence}</code></td><td>{text}</td></tr>"
        )
    lines.append("</table>")
    return "".join(lines)


def _themes_list() -> str:
    items = "".join(
        f"<li>{tr(name)}<code style='color:#888'>（{key}）</code></li>"
        for key, name in theme.theme_names()
    )
    return f"<ul>{items}</ul>"


def _engines_table(current: str = "") -> str:
    from .engine import ENGINE_LABELS

    rows = "".join(
        f"<tr><td>{tr(label)}</td></tr>" for label in ENGINE_LABELS.values()
    )
    note = trf('<p>当前使用：<b>{0}</b></p>',
               tr(ENGINE_LABELS.get(current, current or '自动选择'))) if current else ""
    return f"<table cellspacing='0' cellpadding='4' width='100%'>{rows}</table>{note}"


def _search_engines() -> str:
    names = "、".join(item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else str(item)
                     for item in (SEARCH_ENGINES or []))
    return trf('<p>内置搜索引擎：{0}</p>', names or '（见设置）')


def _ua_presets() -> str:
    try:
        from .useragent import UA_PRESETS

        names = [name for name, _value in UA_PRESETS]
        return tr("<p>内置预设：") + "、".join(names) + "</p>"
    except Exception:
        return ""


def _settings_pages() -> str:
    pages = [
        (tr("常规"), tr("主页与启动方式、默认搜索引擎、下载目录、缩放比例")),
        (tr("外观"), tr("UI 风格（XP/98/7/8.1/10）、深色浅色、自定义边框颜色、渲染引擎、工具栏、窗口边框")),
        (tr("性能"), tr("后台标签页挂起与等待时间、会话恢复、DNS 预解析、平滑滚动、图片加载、内存与缓存统计")),
        (tr("网络"), tr("Flash 兼容（Ruffle 无广告 Flash）、User-Agent 预设与自定义、"
              "HTTPS 证书校验方式、可疑网址提示与名单管理")),
        (tr("内核与环境"), tr("WebView2 运行环境自动诊断（系统 / 运行时 / 组件文件 / .NET / 数据目录），"
                    "缺什么点一下就能下载安装")),
        (tr("隐私与安全"), tr("广告与弹窗拦截、无痕浏览、历史记录与保留天数、"
                    "数据加密与口令、Cookie 与缓存清理")),
        (tr("关于"), tr("版本、作者、当前渲染引擎与解码能力")),
    ]
    items = "".join(f"<li><b>{name}</b>：{desc}</li>" for name, desc in pages)
    return f"<ul>{items}</ul>"


# --------------------------------------------------------------------------- #
# 功能说明
# --------------------------------------------------------------------------- #
def sections(window=None, config=None) -> list[Topic]:
    """返回全部帮助主题（可变部分动态生成）。"""
    from .engine import resolve_engine

    current_engine = ""
    try:
        current_engine = getattr(window, "engine_id", "") or resolve_engine("auto")
    except Exception:
        current_engine = ""

    return [
        Topic(
            "start", tr("快速上手"),
            f"""
            <h3>{APP_NAME} {APP_VERSION}</h3>
            <p>{tr('一款用 Python 编写的轻量浏览器，界面为仿 Windows 经典风格，作者')} <b>{AUTHOR}</b>{tr('。')}</p>
            <p><b>视频播不了？</b>先看「帮助 → 视频播放自检」，
            它会直接告诉你当前内核支不支持 H.264。</p>
            <ul>
              <li><b>地址栏</b>：输入网址回车打开；输入关键字则用默认搜索引擎搜索。</li>
              <li><b>标签页</b>：工具栏右侧 <code>+</code> 新建；页面里的
                  <code>target="_blank"</code> 链接会自动开新标签页。</li>
              <li><b>书签</b>：收藏菜单、书签栏、<code>Ctrl+D</code> 添加、整理收藏夹。</li>
              <li><b>设置</b>：菜单「设置 → 设置」，或工具栏齿轮按钮；
                  共 7 页：常规 / 外观 / 性能 / 网络 / 内核与环境 / 隐私与安全 / 关于。</li>
              <li><b>当前版本</b>：状态栏最右侧显示（点击可打开「关于」）。</li>
              <li><b>插件以外的功能都在菜单里</b>：文件（保存 / 打印）、工具（下载 / 历史 /
                  Cookie 与缓存 / 无痕 / 快捷方式）、帮助（帮助 / 视频自检）。</li>
            </ul>
            <p>设置项分布：</p>
            {_settings_pages()}
            """,
            "home",
        ),
        Topic(
            "tab", tr("标签页与导航"),
            """
            <ul>
              <li><b>多标签页</b>：支持拖动排序、中键关闭、<code>Ctrl+Tab</code> 切换。</li>
              <li><b>前进 / 后退 / 停止 / 刷新 / 主页</b>：工具栏按钮，均有快捷键。</li>
              <li><b>页面内查找</b>：<code>Ctrl+F</code> 打开查找栏，显示匹配数量，
                  可上下跳转；<code>Esc</code> 关闭。</li>
              <li><b>缩放</b>：<code>Ctrl+加号 / 减号 / 0</code>，状态栏右下角显示当前比例，
                  可在设置中设定默认值。</li>
              <li><b>全屏</b>：<code>F11</code> 或「查看 → 全屏显示」，
                  全屏时自动隐藏所有工具栏，<code>Esc</code> 退出；网页内的 HTML5 全屏同样支持。</li>
              <li><b>会话恢复</b>：在「设置 → 性能」打开后，下次启动会恢复上次的标签页
                  （只加载第一个，其余点击时再加载，以加快启动）。</li>
            </ul>
            """,
            "tab_new",
        ),
        Topic(
            "bookmark", tr("书签（收藏夹）"),
            """
            <ul>
              <li><b>添加</b>：<code>Ctrl+D</code> 或工具栏星标按钮，可修改名称与地址。</li>
              <li><b>书签栏</b>：菜单「查看 → 书签栏」显示 / 隐藏，点「整理」可编辑、删除、排序。</li>
              <li><b>整理收藏夹</b>：<code>Ctrl+Shift+O</code>，支持上移 / 下移 / 改名 / 改地址 / 删除。</li>
              <li><b>存储</b>：书签经 <b>AES-256-GCM</b> 加密后保存在
                  <code>%APPDATA%\\LiteBrowser\\data\\bookmarks.dat</code>。</li>
            </ul>
            """,
            "star",
        ),
        Topic(
            "download", tr("下载管理"),
            """
            <ul>
              <li><b>打开</b>：<code>Ctrl+J</code> 或「工具 → 下载管理」。</li>
              <li><b>目录</b>：<b>第一次下载时</b>会让你选择保存目录，之后默认使用它；
                  随时可在下载窗口或「设置 → 常规」中修改，也可勾选「每次下载都询问」。</li>
              <li><b>信息</b>：实时显示进度、已下载 / 总大小、速度与状态，
                  支持打开文件、打开所在文件夹、取消、删除、清除已完成。</li>
              <li><b>下载完成提示</b>：完成后右下角会弹出气泡，显示文件名与保存位置，
                  点右上角 × 可立即关闭；鼠标停在上面时不会消失，移开后 2 秒自动关闭，
                  无人操作则 5 秒后自动消失；点气泡本体可直接打开所在文件夹。</li>
              <li><b>记录</b>：下载记录同样加密保存，可在下载窗口中清除。</li>
            </ul>
            """,
            "download",
        ),
        Topic(
            "history", tr("历史记录"),
            """
            <ul>
              <li><b>打开</b>：<code>Ctrl+H</code> 或「工具 → 历史记录」。</li>
              <li><b>按日期分组</b>：每一条都标注了打开的<b>日期（含星期）与时间</b>，
                  同一地址自动合并并显示访问次数。</li>
              <li><b>搜索</b>：顶部搜索框按标题或网址筛选，<b>命中的关键字会用荧光笔高亮显示</b>，
                  支持中文与网址片段。</li>
              <li><b>操作</b>：搜索、双击打开、删除单条、按时间范围清除、清空全部。</li>
              <li><b>保留策略</b>：在「设置 → 隐私与安全」中可关闭记录，或设定保留天数
                  （超过天数的记录在启动时自动清理）。</li>
            </ul>
            """,
            "history",
        ),
        Topic(
            "incognito", tr("无痕浏览"),
            """
            <ul>
              <li><b>开关</b>：工具栏「无痕」按钮、<code>Ctrl+Shift+N</code>，
                  或「设置 → 隐私与安全」。</li>
              <li><b>效果</b>：浏览历史不写入磁盘；Cookie 与缓存仅保存在内存中，
                  关闭程序后不保留。状态栏会显示红色的「无痕浏览」标识。</li>
              <li><b>实现</b>：WebView2 使用 InPrivate 模式，QtWebEngine 使用内存 profile。
                  切换模式会重新打开标签页。</li>
            </ul>
            """,
            "incognito",
        ),
        Topic(
            "crypto", tr("数据加密与解密"),
            """
            <ul>
              <li><b>算法</b>：AES-256-GCM（带认证，防篡改），文件格式为
                  <code>LTB1</code> 魔数 + 版本 + 12 字节随机 nonce + 密文。</li>
              <li><b>加密对象</b>：书签、历史记录、下载记录。</li>
              <li><b>主密钥</b>：保存为 <code>master.key</code>，
                  默认由 <b>Windows DPAPI</b> 保护（只有同一 Windows 账户能解开）。</li>
              <li><b>口令保护</b>：「设置 → 隐私与安全 → 数据加密」可设置口令
                  （scrypt 派生密钥），便于把数据带到别的机器；启动时需要输入口令。</li>
              <li><b>解密工具</b>：菜单「工具 → 导出明文数据」把加密文件导出为 JSON，
                  也可用源码目录里的 <code>tools\\decrypt_data.py</code>。</li>
            </ul>
            """,
            "lock",
        ),
        Topic(
            "data", tr("Cookie 与缓存管理"),
            """
            <ul>
              <li><b>入口</b>：<code>Ctrl+Shift+Del</code>、「工具 → Cookie 与缓存管理」，
                  或「设置 → 隐私与安全 → Cookie 与缓存」。</li>
              <li><b>Cookie</b>：列出域名、名称、路径、是否安全、过期时间；
                  可按关键字筛选，支持删除所选、删除全部、删除会话 Cookie。</li>
              <li><b>缓存</b>：显示磁盘缓存与用户配置目录的实际占用，
                  可清除缓存、清除站点数据（localStorage / IndexedDB）、
                  一键清理全部浏览数据（不会删除书签、历史与下载记录）。</li>
              <li><b>磁盘缓存上限</b>：在「设置 → 性能」中设定（WebView2 以命令行开关生效，
                  重启后应用）。</li>
            </ul>
            """,
            "settings",
        ),
        Topic(
            "saveprint", tr("网页保存与打印"),
            """
            <ul>
              <li><b>页面另存为</b>：<code>Ctrl+S</code>，可选三种格式 ——
                  <b>MHTML 单文件</b>（.mhtml，把页面与图片样式打包成一个文件，适合存档）、
                  <b>完整网页</b>（html + 同名资源文件夹）、<b>仅 HTML</b>（只存 HTML）。</li>
              <li><b>打印</b>：<code>Ctrl+P</code>。WebView2 内核直接调起系统打印对话框；
                  QtWebEngine 内核会先生成打印预览 PDF 再交给系统阅读器。</li>
              <li><b>导出 PDF</b>：菜单「文件 → 导出为 PDF」。</li>
              <li><b>提示</b>：MHTML 由内核快照功能生成，最忠实还原页面。</li>
            </ul>
            """,
            "save",
        ),
        Topic(
            "theme", tr("主题与界面自定义"),
            f"""
            <ul>
              <li><b>{len(theme.THEME_ORDER)}{tr(' 种 UI 风格')}</b>{tr('：「设置 → 外观 → 界面风格」，')}
                  {tr('切换立即生效，无需重启。')}</li>
              {_themes_list()}
              <li><b>深色 / 浅色</b>：同一位置切换，所有对话框（含设置页内的说明文字）
                  都会跟着变换，保证可读性；也可以用菜单
                  「查看 → 深色模式」（<code>Ctrl+Shift+D</code>）快速切换。
                  <b>选择会被记住</b>，下次启动保持上次的模式。</li>
              <li><b>自定义边框颜色</b>：勾选「自定义边框颜色」后选色，
                  标题栏与窗口边框会一起使用该颜色；点「用主题默认值」恢复。</li>
              <li><b>系统原生窗口边框</b>：勾选后使用 Windows 自己的标题栏
                  （经典 XP 外观请勿勾选），需重启生效。</li>
            </ul>
            """,
            "settings",
        ),
        Topic(
            "perf", tr("性能与内存优化"),
            """
            <ul>
              <li><b>后台标签页自动挂起</b>：闲置超过设定时间（默认 10 分钟）的标签页
                  会被内核挂起，释放渲染进程内存；切回该标签页时自动恢复，
                  滚动位置与表单内容不会丢失。</li>
              <li><b>隐藏标签页停止渲染</b>：只显示当前标签页的内容，降低 CPU 占用。</li>
              <li><b>DNS 预解析（默认关闭）</b>：开启后会对当前页面里的链接域名做
                  dns-prefetch / preconnect，加快点击后的打开速度；
                  <b>隐私提示</b>：这会让这些域名的服务器在你实际点击之前
                  就收到 DNS 查询或连接，相当于提前暴露"你访问过当前页面"，
                  因此在「设置 → 性能」里默认是关闭的。</li>
              <li><b>平滑滚动 / 图片开关</b>：可按需开启或关闭图片以提速省流量。</li>
              <li><b>运行状态</b>：「设置 → 性能」显示主进程内存、磁盘缓存、用户配置占用、
                  标签页数与挂起数量，以及上次启动耗时；可一键挂起后台标签页或清理缓存。</li>
            </ul>
            """,
            "settings",
        ),
        Topic(
            "security", tr("安全：证书校验与可疑网址提示"),
            """
            <ul>
              <li><b>连接状态指示</b>：地址栏左侧图标显示当前页面的<b>传输层</b>状态 ——
                  绿色挂锁 = HTTPS 加密连接（证书校验通过），
                  黄色警告 = HTTP 未加密连接；点击可查看详情。
                  注意：HTTPS 只说明"连接经过 TLS 加密且证书验证通过"，
                  <b>不代表网站本身可信</b>。</li>
              <li><b>证书校验</b>：证书异常（过期、名称不符、自签名等）时弹出详情对话框，
                  显示访问的网站、问题、颁发给、颁发者与有效期，由你决定是否继续；
                  也可在「设置 → 网络」打开<b>严格模式</b>直接拒绝。</li>
              <li><b>可疑网址提示</b>：命中本地规则时会暂停打开并给出提示，规则包括黑名单命中、
                  IP 直连、非常规端口、punycode 同形异义域名、<code>@</code> 伪装、
                  敏感词 + 非 HTTPS、高风险域名后缀、子域名层级过多、网址异常冗长等。
                  这些是<b>启发式规则</b>，只用于识别可疑的 URL 特征，
                  不等同于恶意网址信誉数据库或杀毒软件。</li>
              <li><b>名单文件</b>：<code>%APPDATA%\\LiteBrowser\\blocklist.txt</code>，
                  每行一个域名，<code>#</code> 注释，<code>!</code> 开头为白名单；
                  也可在「设置 → 隐私与安全」中维护。</li>
              <li><b>误拦截</b>：提示页上点「我了解风险，继续访问」可临时放行。</li>
            </ul>
            """,
            "warn",
        ),
        Topic(
            "ua", tr("User-Agent（用户代理）"),
            f"""
            <ul>
              <li><b>位置</b>：「设置 → 网络 → User-Agent」。</li>
              <li><b>预设</b>：一键切换常见浏览器与设备标识（Windows Chrome / Edge / Firefox、
                  macOS Safari、Linux、Android、iPhone、iPad、微信内置浏览器）。</li>
              <li><b>自定义</b>：选择「自定义」后填入任意 UA；
                  <b>清空内容即恢复内核默认值</b>。</li>
              <li><b>用途</b>：访问只为手机提供页面的站点、绕过某些客户端的 UA 限制等。
                  界面下方会实时显示当前生效的 UA 字符串。</li>
            </ul>
            {_ua_presets()}
            """,
            "globe",
        ),
        Topic(
            "engine", tr("渲染引擎说明"),
            f"""
            <p>{tr('程序内置两种 Chromium 内核，启动时自动选择，也可在')}
            {tr('「设置 → 外观 → 渲染引擎」强制指定（切换后需重启程序）。')}</p>
            {_engines_table(current_engine)}
            <ul>
              <li><b>Edge WebView2</b>（默认）：使用系统自带 Edge 运行时，
                  含 H.264 / AAC 等完整编解码器，哔哩哔哩等站点可正常播放视频；</li>
              <li><b>QtWebEngine</b>：随程序打包，无需系统组件，
                  但官方二进制包只有开源编解码器，部分视频站点会提示不支持。</li>
            </ul>
            """,
            "globe",
        ),
        Topic(
            "video", tr("视频播放（哔哩哔哩等）"),
            f"""
            <p>程序内置两种内核，<b>只有 Edge WebView2 含 H.264/AAC 专有编解码器</b>，
            哔哩哔哩等站点依赖它们才能播放。</p>
            <ul>
              <li><b>自检工具</b>：菜单「帮助 → 视频播放自检」会打开一个页面，
                  直接列出当前内核、WebView2 版本、H.264/AAC/H.265/AV1 支持情况，
                  并播放一段测试视频。</li>
              <li><b>提示"不支持 HTML5 播放器"</b>：说明当前用的是 QtWebEngine 内核。
                  到「设置 → 外观 → 渲染引擎」选择
                  <b>Edge WebView2（Chromium，含 H.264/AAC）</b>，确定后<b>重启程序</b>。</li>
              <li><b>番剧 / 影视 / 1080P 以上清晰度播不了</b>：这些内容要求<b>先登录</b>
                  哔哩哔哩账号，未登录时页面会显示「出错啦」或要求登录，属于站点限制。</li>
              <li><b>后台播放被中断</b>：后台标签页闲置过久会被挂起以节省内存。
                  正在播放音频或视频的标签页<b>会自动跳过挂起</b>；
                  如需完全关闭，可在「设置 → 性能」里取消勾选自动挂起。</li>
              <li><b>播放卡顿或黑屏</b>：可先用「工具 → Cookie 与缓存管理」清理缓存，
                  再刷新页面；也可以按 F12 打开开发者工具查看具体报错。</li>
              <li><b>测试地址</b>：
                  <a href="{BILI_VIDEO}">{BILI_VIDEO}</a></li>
            </ul>
            """,
            "globe",
        ),
        Topic(
            "env", tr("内核与环境诊断"),
            """
            <p>程序依赖系统的 <b>Edge WebView2 运行时</b>渲染网页。若它缺失或损坏，
            网页会打不开。为此提供了内置诊断工具：</p>
            <ul>
              <li><b>打开</b>：「设置 → 内核与环境」。</li>
              <li><b>自动检测</b>：操作系统与位数、WebView2 运行时（读注册表，含用户级安装）、
                  随程序分发的组件文件、pythonnet 互操作组件、.NET 运行时、用户数据目录可写性，
                  每项都给出「正常 / 注意 / 异常」与处理建议。</li>
              <li><b>一键修复</b>：点「下载并安装 WebView2 运行时」会从微软官方下载引导安装器
                  （约 2 MB）并启动安装，安装完成后回到该页点「重新检测」即可；
                  也可以点「打开官方下载页」手动下载。</li>
              <li><b>诊断报告</b>：支持一键复制到剪贴板或保存为 txt，反馈问题时很有用。</li>
              <li><b>命令行自检</b>：在命令行执行
                  <code>lite browser.exe --env-report</code>，
                  程序不打开界面，会直接把报告保存到数据目录的
                  <code>env-report.txt</code> 并提示位置，
                  适合网页完全打不开、进不了设置时使用。</li>
              <li><b>相关的还有</b>：「帮助 → 视频播放自检」看解码能力，
                  「设置 → 外观 → 渲染引擎」切换内核。</li>
            </ul>
            """,
            "settings",
        ),
        Topic(
            "flash", tr("Flash 小游戏（无广告）"),
            f"""
            <p><b>先说结论</b>：Adobe Flash Player 已经在 2020 年底停止支持，
            Chromium 内核（含本程序使用的 WebView2）从 88 版起
            <b>彻底移除了 Flash 插件接口</b>，所以"官方 Flash"无法再装进本程序，
            它的广告也无法通过安装插件的方式去掉。</p>
            <p>本程序内置的是 GitHub 上开源的 <b>Ruffle</b>
            （{_ruffle_text()}，Rust 编写的 Flash 运行时，编译成 WebAssembly），
            它能在现代内核里直接运行 Flash 内容，<b>完全没有广告</b>，
            并且会让网页以为自己装了 Flash。</p>
            <ul>
              <li><b>开关</b>：「设置 → 网络 → Flash 兼容（Ruffle，无广告）」，默认开启；
                  也可以点菜单「工具 → Flash 兼容」快速切换。</li>
              <li><b>原理</b>：程序把 Ruffle 放在一个虚拟地址
                  <code>ruffle.litebrowser.local</code> 上供网页加载，
                  并自动把页面里指向 .swf 的地址改成由本程序代取
                  （很多 Flash 站点不发跨域头，直接取会失败）。</li>
              <li><b>直接玩某个 Flash 游戏</b>：如果知道 .swf 地址，
                  直接粘到地址栏回车，程序会用内置播放器打开它。</li>
              <li><b>4399 小游戏</b>：老游戏页（<code>/flash/数字.htm</code>）
                  点「开始游戏」即可；注意 4399 有<b>健康系统</b>，
                  未登录时会提示"先登录，再游戏"，这是站点要求，不是浏览器问题。</li>
              <li><b>兼容性</b>：Ruffle 对 ActionScript 1/2 支持很好，AS3 大部分可用，
                  但复杂 3D、部分老旧加密游戏仍可能跑不起来，
                  这是模拟器的固有限制。</li>
              <li><b>需要 WebView2 内核</b>：QtWebEngine 无法把本地 Ruffle 提供给网页。</li>
            </ul>
            """,
            "globe",
        ),
        Topic(
            "adblock", tr("广告与弹窗拦截"),
            """
            <p>广告屏蔽分两部分：<b>自动拦截弹窗</b> 与 <b>手动标记要屏蔽的元素</b>。</p>
            <ul>
              <li><b>拦截自动弹窗</b>：默认开启（「设置 → 隐私与安全」）。
                  网页脚本在<b>没有用户点击</b>的情况下弹出的窗口会被直接拦掉，
                  状态栏会提示拦截数量；你自己点击链接打开的新标签页不受影响。</li>
              <li><b>手动标记广告</b>：按 <code>Ctrl+Shift+A</code>
                  （或「工具 → 标记并屏蔽广告元素」），
                  页面上会进入点选模式：鼠标移动时红框高亮当前元素，
                  <b>点一下就记下这条规则</b>，按 <code>Esc</code> 取消。
                  之后打开同一网站会自动隐藏它。</li>
              <li><b>规则管理</b>：「工具 → 广告屏蔽规则」，
                  可按网站查看、删除、清空，也可以点「打开该网站」回到那个页面。</li>
              <li><b>规则保存在哪</b>：数据目录下的 <code>adblock.json</code>，
                  明文 JSON，方便你自己备份或手工编辑。</li>
              <li><b>怎么选元素</b>：点广告的<b>外框容器</b>最稳；
                  如果选择器太通用（会命中很多元素），
                  程序会自动退化为更精确的写法，误伤正常内容的可能性很低。</li>
            </ul>
            """,
            "warn",
        ),
        Topic(
            "shortcut", tr("快捷键一览"),
            tr("<p>下表由程序当前注册的快捷键自动生成，功能增删后会自动同步。</p>")
            + _shortcuts_table(window),
            "find",
        ),
        Topic(
            "faq", tr("常见问题"),
            """
            <dl>
              <dt>为什么有些视频网站提示「不支持 HTML5 播放器」？</dt>
              <dd>说明当前用的是 QtWebEngine 内核（不含 H.264）。到
                  「设置 → 外观 → 渲染引擎」切换为 <b>Edge WebView2</b> 并重启即可。
                  也可以用菜单「帮助 → 视频播放自检」确认当前内核的解码能力。</dd>

              <dt>哔哩哔哩的番剧、影视提示「出错啦」？</dt>
              <dd>这些内容需要先登录账号（部分还需大会员）。在页面右上角登录后即可观看。</dd>

              <dt>切换主题 / 深色模式需要重启吗？</dt>
              <dd>不需要，设置里改完立即生效；点「取消」会还原原来的外观。</dd>

              <dt>后台标签页被挂起后，网页里的音乐或视频会停吗？</dt>
              <dd>会暂停，切回该标签页会自动恢复。如不需要，可在「设置 → 性能」关闭自动挂起。</dd>

              <dt>数据放在哪里？换电脑怎么带走？</dt>
              <dd>都在 <code>%APPDATA%\\LiteBrowser</code>。书签 / 历史 / 下载记录是加密的，
                  要迁移请先设置<b>口令</b>（否则其它机器的 DPAPI 解不开），
                  或先用「导出明文数据」导出 JSON。</dd>

              <dt>便携版怎么创建桌面图标？</dt>
              <dd>菜单「工具 → 创建桌面快捷方式」，
                  也可以同时创建开始菜单快捷方式。</dd>
            </dl>
            """,
            "info",
        ),
        Topic(
            "about", tr("关于与版权"),
            f"""
            <ul>
              <li>{tr('名称：')}<b>{APP_NAME}</b></li>
              <li>{tr('版本：')}<b>{APP_VERSION}</b></li>
              <li>{tr('作者：')}<b>{AUTHOR}</b></li>
              <li>{tr('版权：')}{COPYRIGHT}</li>
              <li>技术栈：Python + PySide6（Qt 6）+ Edge WebView2 / QtWebEngine + pythonnet</li>
              <li>界面图标全部由代码绘制，不含任何第三方素材。</li>
            </ul>
            <p>本帮助内容会随功能更新同步维护：快捷键、主题、引擎、UA 预设等
            直接从程序读取，功能说明随版本修订。</p>
            """,
            "app",
        ),
    ]


# --------------------------------------------------------------------------- #
# 帮助窗口
# --------------------------------------------------------------------------- #
class HelpDialog(XPDialog):
    """使用帮助窗口：左侧目录，右侧内容。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        window=None,
        config=None,
        initial: str = "start",
    ) -> None:
        super().__init__(parent, title=trf('{0} 使用帮助', APP_NAME), icon_name="info")
        self.window_ref = window
        self.config = config
        self._topics = sections(window, config)
        self.setMinimumSize(760, 560)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        header = QLabel(
            trf("<b>{0} {1}</b>\u3000作者：{2}\u3000<span style='color:#888'>（本帮助随功能更新同步维护）</span>", APP_NAME, APP_VERSION, AUTHOR)
        )
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal, self)
        self.tree = QTreeWidget()
        self.tree.setObjectName("helpTree")
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setMinimumWidth(190)
        self.tree.setMaximumWidth(260)
        for topic in self._topics:
            node = QTreeWidgetItem([topic.title])
            node.setIcon(0, icons.icon(topic.icon, 16))
            node.setData(0, Qt.UserRole, topic.key)
            self.tree.addTopLevelItem(node)
        splitter.addWidget(self.tree)

        self.view = QTextBrowser()
        self.view.setObjectName("helpView")
        self.view.setOpenExternalLinks(True)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        row = QHBoxLayout()
        self.search_hint = QLabel(tr("提示：按 F1 可随时打开本帮助"))
        self.search_hint.setProperty("role", "hint")
        row.addWidget(self.search_hint)
        row.addStretch(1)
        close = QPushButton(tr("关闭"))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

        self.tree.currentItemChanged.connect(self._on_topic_changed)
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept())
        self.show_topic(initial)

    # ------------------------------------------------------------------ #
    def show_topic(self, key: str) -> None:
        for index in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(index)
            if node.data(0, Qt.UserRole) == key:
                self.tree.setCurrentItem(node)
                return
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _on_topic_changed(self, current: QTreeWidgetItem, _previous=None) -> None:
        if current is None:
            return
        key = current.data(0, Qt.UserRole)
        for topic in self._topics:
            if topic.key == key:
                self.view.setHtml(self._render(topic))
                self.view.verticalScrollBar().setValue(0)
                return

    def _render(self, topic: Topic) -> str:
        t = theme.current()
        # 帮助正文很长，走"整行短语翻译"：英文环境下逐行查表替换，
        # 没翻译到的行保持中文，界面不会因此出错
        body = tr_text(topic.body)
        return f"""
        <html><head><meta charset="utf-8">
        <style>
          body {{ font-family: "Microsoft YaHei UI", Tahoma, sans-serif;
                 font-size: 13px; line-height: 1.75; color: {t.text};
                 background: {t.field_bg}; margin: 12px 16px; }}
          h3 {{ color: {t.text if t.dark else t.highlight}; margin: 4px 0 10px; }}
          code {{ background: {t.face}; padding: 1px 4px; border-radius: 3px; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ border-bottom: 1px solid {t.menu_border}; padding: 4px 6px;
                    text-align: left; }}
          th {{ color: {t.text_dim}; font-weight: normal; }}
          ul, ol {{ padding-left: 22px; }}
          dt {{ font-weight: bold; margin-top: 10px; }}
          dd {{ margin: 2px 0 8px 18px; color: {t.text_dim}; }}
          a {{ color: {t.highlight}; }}
        </style></head><body>{body}</body></html>
        """


def shortcut_help_html(window=None) -> str:
    return _shortcuts_table(window)
