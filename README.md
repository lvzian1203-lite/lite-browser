# lite browser

一款使用 **Python** 编写的轻量浏览器，界面完整仿照 **Windows XP (Luna)** 风格，
并内置 **Windows 98 / 7 / 8.1 / 10 / 11 / HarmonyOS / 哈基米** 七套可切换皮肤、深色模式与自定义边框颜色。

渲染引擎支持两种 Chromium 内核，可自动选择：

* **Edge WebView2**（推荐）—— 使用系统自带的 Microsoft Edge 运行时，Chromium 154，
  含 **H.264 / AAC 等完整编解码器**，哔哩哔哩等站点的 HTML5 视频可以正常播放；
* **QtWebEngine** —— Qt 自带内核，跨平台回退方案（官方二进制包只有开源编解码器）。

还内置了 **Ruffle**（开源 Flash 运行时，无广告），Flash 小游戏网站可以直接游玩；
以及**手动标记屏蔽网页广告**与**自动拦截弹窗**。

> 作者：**lvzian**　版本：**1.7.1**　许可证：**MIT**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-blue.svg)](#五使用方式)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB.svg)](requirements.txt)

![主界面](docs/screenshot-main.png)

### 内置无广告 Flash 与广告屏蔽

| 用 Ruffle 运行 Flash 小游戏（4399 等） | 手动标记并屏蔽广告元素（Ctrl+Shift+A） |
| --- | --- |
| ![Flash](docs/screenshot-flash.png) | ![广告屏蔽](docs/screenshot-adblock.png) |

### 界面风格

| Windows 98 | Windows 11 | HarmonyOS（鸿蒙） |
| --- | --- | --- |
| ![Win98](docs/screenshot-theme-win98.png) | ![Win11](docs/screenshot-theme-win11.png) | ![鸿蒙](docs/screenshot-theme-harmony.png) |

| 哈基米（猫猫） | 深色模式 |
| --- | --- |
| ![哈基米](docs/screenshot-theme-cat.png) | ![深色](docs/screenshot-theme-dark.png) |

### 主要面板与工具

| 设置 · 内核与环境（自检 + 一键修复） | 设置 · 网络（Flash 兼容） |
| --- | --- |
| ![内核与环境](docs/screenshot-engine.png) | ![网络](docs/screenshot-network.png) |

| 设置 · 常规 | 设置 · 外观（八套主题） |
| --- | --- |
| ![设置常规](docs/screenshot-settings.png) | ![外观](docs/screenshot-appearance.png) |

| 设置 · 性能（挂起与内存统计） | 设置 · 隐私与安全（广告与弹窗拦截） |
| --- | --- |
| ![性能](docs/screenshot-performance.png) | ![隐私与安全](docs/screenshot-privacy.png) |

| 历史记录（搜索关键字高亮） | 下载完成气泡提示 |
| --- | --- |
| ![历史](docs/screenshot-history.png) | ![气泡](docs/screenshot-toast.png) |

| 自定义错误页（猫追鼠标） | 恶意网址警告 |
| --- | --- |
| ![错误页](docs/screenshot-error-cat.png) | ![警告页](docs/screenshot-warning.png) |

| 视频播放自检 | 使用帮助（F1） |
| --- | --- |
| ![视频自检](docs/screenshot-video-check.png) | ![帮助](docs/screenshot-help.png) |

| 下载管理 | 关于 |
| --- | --- |
| ![下载](docs/screenshot-downloads.png) | ![关于](docs/screenshot-about.png) |

| 启动画面 | 安装向导 |
| --- | --- |
| ![启动画面](docs/screenshot-splash.png) | ![安装向导](docs/screenshot-setup.png) |

---

## ⚠️ Development Note / 开发说明

**English**

> The skeleton code, calculation module, debug and file management parts of this project are
> assisted by DeepSeek Harness. The overall conception, UI design, function planning,
> code integration and manual modification are completed independently by the author.

**中文**

> 开发说明：本项目代码骨架、数值计算、调试与文件管理模块由 DeepSeek Harness 辅助生成；
> 项目整体构思、设计、功能规划、代码整合与人工修改均由作者独立完成。

---

## 一、功能特性

| 功能 | 说明 |
| --- | --- |
| Chromium 内核 | 双引擎：Edge WebView2（Chromium 154）/ QtWebEngine（Chromium 122），启动时自动选择，可在设置中切换 |
| 视频播放 | WebView2 引擎下支持 H.264 / AAC / MP3，哔哩哔哩等站点可正常播放 HTML5 视频 |
| **内置下载模块** | `Ctrl+J` 打开下载管理：进度、速度、大小、状态、打开文件 / 所在文件夹、取消、删除；**首次下载时由用户设定保存目录**，之后默认使用该目录，可随时在下载窗口或设置中修改 |
| **历史记录** | `Ctrl+H` 查看，**按日期分组并标注每个页面打开的日期与时间**，支持**关键字搜索（命中内容荧光笔高亮）**、双击打开、删除、按时间范围清除、清空全部 |
| **下载完成气泡提示** | 下载完成后右下角弹出气泡：「一只路过的哈基米 🐱 帮你将『文件名』放在了：路径，喵喵。」可点 ✕ 关闭，鼠标停留时不消失，无人操作 5 秒自动关闭；点气泡可直接打开所在文件夹 |
| **WebView2 环境自检与修复** | 「设置 → 内核与环境」：自动检测系统与位数、WebView2 运行时（读注册表）、组件文件、pythonnet 互操作组件、.NET 运行时、数据目录可写性，逐项给出「正常 / 注意 / 异常」与建议；缺运行时**一键从微软官方下载并安装**，还可复制 / 保存诊断报告；网页完全打不开时可用命令行 `lite browser.exe --env-report` 直接生成报告 |
| **状态栏版本号** | 底边栏右侧常显当前版本（点击打开「关于」） |
| **无痕浏览模式** | 设置 → 隐私与安全，或工具栏 / `Ctrl+Shift+N` 一键切换；开启后不写入历史记录，Cookie 与缓存仅存内存（WebView2 使用 InPrivate，QtWebEngine 使用内存 profile），状态栏显示红色“无痕浏览”标识 |
| **数据加密** | 书签 / 历史记录 / 下载记录全部使用 **AES-256-GCM** 加密保存，主密钥由 Windows DPAPI 保护，也可设置口令（scrypt 派生）；附带 **明文导出工具**（菜单「工具 → 导出明文数据」或 `tools/decrypt_data.py`） |
| **多套 UI 风格** | 无边框窗口 + 代码绘制的完整皮肤：**Windows XP (Luna) / 98 经典 / 7 (Aero) / 8.1 / 10 / 11（Mica 圆角） / HarmonyOS（鸿蒙） / 哈基米（猫猫）** 八种风格，支持**深色 / 浅色**模式（选择会被记住），并可**自定义边框颜色**（同时作用于标题栏与窗口边框）；切换立即生效，无需重启 |
| **内置无广告 Flash（Ruffle）** | 内置 GitHub 开源 **Ruffle 0.6.0**（Rust + WebAssembly 的 Flash 运行时）：无需插件、**完全没有广告**，并伪造 Flash 插件让老站点不再提示"请安装 Flash"；程序通过虚拟域名给网页供給 Ruffle，并把页面里的 .swf 地址改成由本程序**代取**（绕过站点不发跨域头导致的 CORS 失败）；4399 等 Flash 小游戏实测可玩，直接把 .swf 地址粘到地址栏也能用内置播放器打开 |
| **广告与弹窗拦截** | **`Ctrl+Shift+A` 手动标记**：进入点选模式，红框实时高亮，点一下那个广告/浮层就记住规则，之后打开同一网站自动隐藏（动态插入的也会持续隐藏）；规则按网站保存于 `adblock.json`，可在「工具 → 广告屏蔽规则」查看/删除/清空；**自动拦截非用户点击弹出的窗口**，状态栏显示拦截数量 |
| **性能优化** | 后台标签页闲置后**自动挂起**（WebView2 `TrySuspendAsync` / QtWebEngine `Frozen` 生命周期），切回自动恢复；隐藏标签页停止渲染；可选的 DNS 预解析、平滑滚动、图片开关、磁盘缓存上限；设置中实时显示内存与缓存占用 |
| **Cookie 与缓存管理** | 「设置 → 隐私与安全」与「工具 → Cookie 与缓存管理」(`Ctrl+Shift+Del`)：列出全部 Cookie（域名 / 名称 / 路径 / 安全 / 过期时间）并支持搜索、删除所选、删除全部、删除会话 Cookie；清除缓存、清除站点数据、一键清理全部浏览数据 |
| **自定义错误页** | 网络错误与 HTTP 4xx/5xx 都会显示自绘错误页：**一只追着鼠标指针跑的猫**（走路时留下脚印，靠近时跳一下），显示状态码、说明、网址，并提供重新加载 / 返回上一页 / 回到主页 |
| **HTTPS 证书校验** | 证书异常时弹出详情对话框（访问的网站、问题、颁发给、颁发者、有效期），由用户决定是否继续；也可开启「严格模式」直接拒绝；地址栏左侧实时显示连接安全性（挂锁 / 警告） |
| **恶意网址警告** | 本地判定引擎：黑名单 / 白名单文件 + 启发式规则（IP 直连、非标准端口、punycode 同形异义、`@` 伪装、敏感词、高风险后缀、超长子域名、超长网址…），命中后显示红色警告页，可返回或「我了解风险，继续访问」 |
| **网页保存 / 打印** | 文件菜单：另存为（**MHTML 单文件** / 完整网页 / 仅 HTML，`Ctrl+S`）、**打印**（`Ctrl+P`，WebView2 直接调起系统打印；QtWebEngine 生成打印预览 PDF）、**导出 PDF** |
| **User-Agent 可修改** | 「设置 → 网络」：内置 Windows Chrome/Edge/Firefox、macOS Safari、Linux、Android、iPhone/iPad、微信等预设，也可完全自定义，实时预览生效值 |
| 仿 WinXP 界面 | 无边框窗口 + Luna 蓝色渐变标题栏、圆角、XP 风格工具栏 / 菜单 / 标签页 / 状态栏 / 滚动条，图标全部由代码绘制 |
| 书签 | 收藏菜单、书签栏、`Ctrl+D` 添加、整理收藏夹（编辑 / 删除 / 排序 / 打开），加密存储 |
| 全屏显示 | `F11` 或菜单「查看 → 全屏显示」，全屏时自动隐藏所有工具栏，`Esc` 退出，也支持网页内 HTML5 全屏 |
| 自定义首页 | 「设置 → 常规」中可自定义主页地址，支持“使用当前页 / 使用默认页 / 使用空白页” |
| 设置 - 关于 | 「设置 → 关于 lite browser」中显示名称、版本、**作者：lvzian**、当前渲染引擎与解码能力 |
| 多标签页 | 新建 / 关闭 / 拖动排序，`+` 按钮新建标签页，`target="_blank"` 自动开新标签页 |
| 地址栏搜索 | 输入关键字自动调用所选搜索引擎（必应 / 百度 / Google / 搜狗 / DuckDuckGo） |
| 其它 | 前进后退、停止刷新、主页、页面内查找(`Ctrl+F`)、缩放、开发者工具(`F12`)、另存为、查看源代码、上次会话恢复、窗口位置记忆 |
| 外部调用 | 支持命令行传入网址：`"lite browser.exe" https://www.example.com` |
| **帮助系统** | 「帮助 → 使用帮助」(`F1`)：19 个主题逐项解释功能的作用与用法；快捷键、UI 风格、渲染引擎、UA 预设等**从程序读取**，随功能更新自动同步 |
| **深色模式记忆** | 「查看 → 深色模式」(`Ctrl+Shift+D`) 快速切换，选择写入配置，下次启动保持上次的模式 |
| **视频播放自检** | 「帮助 → 视频播放自检」：显示当前引擎、WebView2 版本、H.264/AAC/H.265/AV1 与 MSE 支持，并播放测试视频；播不了时直接给出切换内核的步骤 |
| **桌面快捷方式** | 「工具 → 创建桌面快捷方式 / 创建开始菜单快捷方式」，便携版也可一键生成 |
| **启动优化** | 约 0.19 秒显示启动画面、约 2.7 秒打开首页（打包版热启动）；.NET Framework 托管 WebView2、样式表延后统一应用、状态栏单容器、WebView2 环境预热并全标签页共享 |

---

## 二、渲染引擎说明

| | Edge WebView2 | QtWebEngine |
| --- | --- | --- |
| 内核版本 | Chromium 154（随 Edge 更新） | Chromium 122（随 Qt 更新） |
| H.264 / AAC | ✅ 支持 | ❌ 不支持 |
| 哔哩哔哩等视频站 | ✅ 可播放 | ❌ 提示“不支持 HTML5 播放器” |
| 运行依赖 | Windows 10/11 自带的 WebView2 运行时 | 无（随程序打包） |
| 数据目录 | `%APPDATA%\LiteBrowser\webview2` | `%APPDATA%\LiteBrowser\profile` |

程序启动时会自动检测：能用 WebView2 就用 WebView2，否则回退到 QtWebEngine。
也可以在「设置 → 外观 → 渲染引擎」中强制指定（切换后需重启程序）。

---

## 三、数据加密与解密工具

### 加密方式

| 项目 | 说明 |
| --- | --- |
| 算法 | AES-256-GCM（带认证，防篡改） |
| 加密文件 | `data\bookmarks.dat`、`data\history.dat`、`data\downloads.dat` |
| 文件格式 | 4 字节魔数 `LTB1` + 版本号 + 12 字节随机 nonce + 密文 |
| 主密钥 | `master.key`，32 字节随机密钥 |
| 默认保护 | **Windows DPAPI**（`CryptProtectData`），只有同一 Windows 账户能解开 |
| 可选保护 | **口令**（scrypt n=2^14, r=8, p=1 派生密钥），便于跨机携带；启动时提示输入 |

在「设置 → 隐私与安全 → 数据加密」中可以设置 / 取消口令，并查看当前加密状态。

### 解密工具

**方式一（图形界面）**：菜单「工具 → 导出明文数据...」，选择输出目录即可。

**方式二（命令行）**：

```bat
rem 查看数据目录与加密状态
python tools\decrypt_data.py --list

rem 解密到 .\decrypted（DPAPI 保护的密钥需要同一 Windows 账户）
python tools\decrypt_data.py --out D:\备份

rem 设置过口令时
python tools\decrypt_data.py --password 你的口令 --out D:\备份

rem 指定数据目录（例如绿色便携模式）
python tools\decrypt_data.py --data-dir D:\litebrowser\data --out D:\备份
```

导出结果：`bookmarks.json`、`history.json`、`downloads.json`（格式化后的明文 JSON）。

> 注意：DPAPI 模式下密钥与 Windows 账户绑定，换机器 / 换账户无法解密；
> 如需跨机备份，请先在设置中设置口令，再用口令解密。

---

## 四、目录结构

```
liulanqi/
├─ lite_browser.py          程序入口（源码方式启动）
├─ litebrowser/             程序主体包
│  ├─ main.py               应用初始化（引擎选择、保险库解锁、样式、DPI）
│  ├─ browser.py            浏览器主窗口（标签页、地址栏、书签栏、全屏、菜单）
│  ├─ engine.py             渲染引擎抽象层与工厂
│  ├─ wv2engine.py          Edge WebView2 引擎后端（H.264/AAC、Ruffle 资源供给）
│  ├─ qtengine.py           QtWebEngine 引擎后端（回退方案）
│  ├─ ruffle.py             内置无广告 Flash 运行时（Ruffle）的供给与 .swf 代取
│  ├─ safefetch.py          带 SSRF 防护的受限 HTTP 抓取（逐跳校验 + IP 钉住）
│  ├─ logging_setup.py      统一日志（默认不输出，LITE_BROWSER_LOG=1 写文件）
│  ├─ adblock.py            用户手动标记的广告屏蔽（规则存储 + 点选脚本）
│  ├─ webview2doctor.py     运行环境自检与一键修复
│  ├─ videocheck.py         视频播放自检页
│  ├─ errors.py             自定义错误页（猫追鼠标）与可疑网址提示页
│  ├─ netsec.py             证书校验与可疑网址启发式判定
│  ├─ crypto.py             数据加密：AES-256-GCM + DPAPI / 口令
│  ├─ bookmarks.py          书签存储（加密）
│  ├─ history.py            历史记录（加密，按日期分组）
│  ├─ downloads.py          下载管理（目录规则、进度、记录）
│  ├─ managers.py           下载管理器窗口、历史记录窗口（搜索高亮）
│  ├─ datamanage.py         Cookie 与缓存管理窗口
│  ├─ performance.py        后台挂起、内存与缓存统计
│  ├─ useragent.py          User-Agent 预设
│  ├─ shelllink.py          创建桌面 / 开始菜单快捷方式
│  ├─ help.py               帮助系统（内容随功能自动同步）
│  ├─ widgets.py            仿 XP 窗口框架：标题栏、无边框窗口、气泡提示
│  ├─ dialogs.py            设置（7 页）/ 书签 / 广告规则对话框
│  ├─ config.py             配置与路径管理
│  ├─ theme.py              八套主题配色与全局 QSS / 调色板
│  └─ icons.py              全部图标的代码绘制（无需图片资源）
├─ lib/webview2/            WebView2 程序集（随程序分发）
├─ lib/ruffle/              内置 Ruffle（含 MIT / Apache-2.0 许可文件）
├─ tools/
│  ├─ make_icon.py          生成 assets/lite_browser.ico
│  ├─ decrypt_data.py       【解密工具】导出明文 JSON
│  ├─ build_installer.py    构建 Windows 安装包与便携版
│  ├─ installer/            安装程序 / 卸载程序的 C# 源码
│  ├─ slim_dist.py          打包后按依赖关系精简体积
│  └─ version_info.txt      exe 版本信息（公司名 lvzian）
├─ assets/  docs/           图标资源 / 截图与解码自检页
├─ tests/                   单元测试（149 个用例，仅依赖标准库 unittest）
├─ .github/workflows/       GitHub Actions：windows 上跑 pytest + ruff
├─ dist/lite browser/       【已打包好的 exe】双击 lite browser.exe 即可运行
├─ run.bat                  源码方式启动
├─ build_exe.bat            一键打包 exe
├─ CHANGELOG.md             完整更新日志（v1.1.0086 起）
├─ ruff.toml                代码检查配置（只查语法错误 / 未定义名等硬问题）
└─ requirements.txt         依赖：PySide6、pythonnet、cryptography
```

---

## 五、使用方式

### 1. 使用安装包安装（推荐，适合分发）

从 Releases 页面下载：

```
lite browser-<版本>-安装程序.exe     （安装包）
lite browser-<版本>-便携版.zip       （免安装，解压即用）
```

双击安装包运行向导即可安装：

* 纯当前用户安装（默认 `%LOCALAPPDATA%\Programs\lite browser`），**不需要管理员权限**
* 可选创建桌面 / 开始菜单快捷方式，可选安装后运行
* 自动注册到 Windows「已安装的应用 / 程序和功能」，可在其中或开始菜单里卸载
* 卸载时可选择是否一并删除个人数据（默认保留）

![安装向导](docs/screenshot-setup.png)

静默安装（批量部署）：

```bat
"lite browser-<版本>-安装程序.exe" /S /DIR="D:\Program Files\lite browser"
rem 可选：/NODESKTOP /NOSTARTMENU /NORUN
```

便携版解压后双击 `lite browser.exe` 即可使用，
也可以用菜单「工具 → 创建桌面快捷方式」生成桌面图标。

### 2. 直接运行打包好的程序

```
dist\lite browser\lite browser.exe
```

### 3. 从源码运行

```bat
pip install -r requirements.txt
python lite_browser.py
```

### 4. 自己重新打包

```bat
build_exe.bat                                  rem 打包程序到 dist\lite browser
python tools\build_installer.py --portable     rem 生成安装包与便携版（默认输出到当前目录）
```

`tools\build_installer.py` 会用系统自带的 C# 编译器（.NET Framework 4.x 的 `csc.exe`）
把 `tools\installer\installer.cs` / `uninstaller.cs` 编译成原生安装程序与卸载程序，
再把程序目录压缩后附加到安装程序 exe 末尾（附加 12 字节尾部标记，供安装程序自读）。

### 5. 运行测试

测试只依赖 Python 标准库 `unittest`（`pytest` 可选），无需安装额外依赖：

```bat
python -m unittest discover -s tests -t .      rem 运行全部单元测试
python -m unittest tests.test_safefetch -v     rem 只跑某一个模块
```

共 **149 个用例**，覆盖 SSRF 防护（地址类别、scheme、跳转链与次数上限、体积与类型限制）、
Ruffle 会话 token、可疑网址判定的误报/漏报统计、广告屏蔽规则与注入脚本、
AES-256-GCM 加解密与失败路径、历史记录 / 下载管理 / 配置 / 地址栏输入归一化。

仓库还带有 GitHub Actions 工作流（`.github/workflows/tests.yml`）：
在 **windows-latest + Python 3.13** 上执行 `ruff check litebrowser tests` 与
`python -m pytest tests -v`，在 Pull Request 与 main 分支推送时自动运行。

> 排查问题时设置环境变量 `LITE_BROWSER_LOG=1`，日志会写入数据目录的
> `litebrowser.log`（默认不输出日志）；`LITE_BROWSER_TIMING=1` 另外记录启动耗时。

---

## 六、快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl+T` / `Ctrl+W` | 新建 / 关闭标签页 |
| `Ctrl+J` | 下载管理 |
| `Ctrl+H` | 历史记录 |
| `Ctrl+Shift+N` | 切换无痕浏览模式 |
| `Ctrl+D` / `Ctrl+Shift+O` | 添加到收藏夹 / 整理收藏夹 |
| `Ctrl+L` / `Ctrl+F` | 定位地址栏 / 页面内查找 |
| `Ctrl+S` / `Ctrl+P` | 页面另存为 / 打印 |
| `Ctrl+Shift+Del` | Cookie 与缓存管理 |
| `F1` | 使用帮助 |
| `Ctrl+U` / `F12` | 查看源代码 / 开发者工具 |
| `F5` / `Ctrl+R` | 刷新 |
| `F11` | 全屏显示 / 退出全屏 |
| `Esc` | 退出全屏、关闭查找栏 |
| `Ctrl+ +` / `Ctrl+ -` / `Ctrl+0` | 放大 / 缩小 / 实际大小 |
| `Alt+←` / `Alt+→` | 后退 / 前进 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 切换标签页 |
| `Alt+F4` | 退出 |

---

## 七、数据文件位置

| 内容 | 路径 |
| --- | --- |
| 设置 | `%APPDATA%\LiteBrowser\settings.json` |
| 书签（加密） | `%APPDATA%\LiteBrowser\data\bookmarks.dat` |
| 历史记录（加密） | `%APPDATA%\LiteBrowser\data\history.dat` |
| 下载记录（加密） | `%APPDATA%\LiteBrowser\data\downloads.dat` |
| 主密钥 | `%APPDATA%\LiteBrowser\master.key` |
| 内核缓存 / Cookies | `%APPDATA%\LiteBrowser\profile`、`webview2` |

> 绿色便携模式：在 `lite browser.exe` 同级目录放入一个空的 `portable.txt`，
> 数据就会改为保存在程序目录的 `data` 子文件夹中。
> 旧版本的明文 `bookmarks.json` 会在首次启动时自动加密迁移。

---

## 八、常见问题

**Q：哔哩哔哩提示“您当前的浏览器不支持 HTML5 播放器”？**
说明当前用的是 QtWebEngine 引擎（不含 H.264/AAC）。到「设置 → 外观 → 渲染引擎」
选择“Edge WebView2”后重启。也可用本程序打开 `docs/codec-test.html` 自检解码能力。

**Q：下载目录在哪里修改？**
三个入口：① 首次下载时会弹出目录选择；② 下载窗口（`Ctrl+J`）里的“更改...”；
③ 设置 → 常规 → 下载 → 浏览。勾选“每次下载都询问保存位置”可恢复逐个询问。

**Q：无痕模式真的不记录吗？**
开启后不写历史记录，`master.key` 与 `.dat` 文件不会新增浏览痕迹；
Cookie / 缓存位于内存（WebView2 的 InPrivate / QtWebEngine 的内存 profile），
退出程序即消失。注意：下载记录仍会保留（文件已落盘），可在下载窗口中删除。

**Q：忘记加密口令了怎么办？**
口令无法找回。可以删除 `master.key` 与 `data` 目录重新开始（原有加密数据将无法恢复），
或改用其他账户的 DPAPI 密钥。建议设置口令后自行备份 `master.key`。

**Q：网页显示空白 / 花屏？**
QtWebEngine 引擎下可用软件渲染启动：`"lite browser.exe" --disable-gpu`

**Q：想恢复默认设置？**
删除 `%APPDATA%\LiteBrowser` 文件夹后重新启动。

---

## 九、关于

- 名称：**lite browser**
- 版本：**1.7.1**
- 作者：**lvzian**
- 界面风格：Windows XP (Luna) / 98 / 7 / 8.1 / 10（可切换，支持深色模式与自定义边框色）
- 版权：Copyright (C) 2026 lvzian

程序内「设置 → 关于 lite browser」中同样可以看到以上信息。

![关于](docs/screenshot-about.png)

---

## 十、更新记录

完整的分版本更新日志（含每一项功能与修复的说明）见 **[CHANGELOG.md](CHANGELOG.md)**。
下面是近期版本的摘要：

### 1.7.1

本版修一个多标签页正确性缺陷、一个用户直接反馈的地址栏问题、
一个会随使用时间变差的性能问题，并让数据解密工具摆脱 Qt 依赖；
**用户数据格式完全不变**。

1. **修复多标签页错误页互相覆盖**：内置错误页原先用实例级计数器命名
   （每个标签页都从 1 开始 → 同名文件），还会删光共享目录下所有
   `internal-*.html`；结果 A 标签页的错误页被 B 删除/覆盖，刷新后变成
   「文件不存在」。现改为随机 UUID 命名 + 只按时间回收超龄孤儿文件。
2. **修复地址栏回车"没反应"**：用户正在输入时，页面加载完成/重定向上报的
   URL 会把地址栏内容覆盖成旧网址，回车于是"导航到旧网址"；
   现在地址栏有焦点且内容被改动过时不再覆盖，提交后再显示规范化网址。
3. **历史记录改为合并写盘**：原先每次访问都在 UI 线程做
   「全量序列化 + AES 加密 + 同步写盘」，记录越多越慢；
   现由 2 秒定时器统一落盘，退出时 `flush_now()` 保证不丢数据
   （实测连续 20 次访问由 20 次写盘降为 1 次）。
4. **解密工具不再依赖 PySide6**：新增零依赖的 `litebrowser/version.py` +
   包级惰性导入，未安装 Qt 的环境也能用 `tools/decrypt_data.py` 抢救数据
   （数据恢复场景下要求先装 200MB+ 的 Qt 并不合理）。
5. 测试用例 104 → **149**，`ruff` 无告警；另修复非中文系统上命令行工具的中文输出崩溃。

### 1.7.0

本版是一次**安全与工程质量迭代**（按外部 Code Review 清单执行），
不改变产品定位、界面风格与用户数据格式。

1. **安全加固（P0）**
   * **修复 Ruffle 代理的 SSRF 风险**：改为手动逐跳处理跳转（最多 5 次），
     每一跳都重新校验——只允许 `http` / `https`，解析出的**全部** IP 必须是公网地址
     （拒绝 `127.0.0.1`、内网段、`::ffff:127.0.0.1` 等），
     **TCP 连接钉死在已校验的 IP 上**（Host 与 TLS SNI 仍用域名，防 DNS 重绑定），
     并限制响应体积、只接受真正的 SWF（拒绝防盗链 HTML 页面）；
   * **代理不再把 Referer 当唯一授权**：改为按播放会话发放随机 **token**
     （`secrets.token_urlsafe`，带过期与数量上限；随文档轮换、关闭标签页即失效，
     不写入历史记录）。
2. **语义与文案修正（P1）**：明确 netsec 是**本地启发式规则**而不是恶意网址库
   （页面与设置里加免责声明）；「恶意网址」→「**可疑网址**」，
   「安全连接（HTTPS，已加密）」→「**HTTPS 加密连接**」（HTTPS 只说明传输层加密，
   不代表网站可信）；QtWebEngine 弹窗判定改用**用户手势时间窗**；
   AdBlock 注入脚本改为**脏标记 + `requestAnimationFrame` 批处理**；
   101 处静默 `except: pass` 改为带说明的日志（`LITE_BROWSER_LOG=1` 可输出）；
   加密库缺失时**弹窗让用户选择**继续明文或退出，不再静默降级。
3. **架构改进（P2）**：新增 `EngineCapabilities` 能力描述（界面按能力判断，
   不再比较 `engine_id`）、`EngineState` 状态机、`TaskBridge`（统一 .NET Task 轮询）；
   DNS 预解析补充隐私说明（默认仍关闭）。`browser.py` 的拆分**留待后续版本**。
4. **测试与 CI（P4 / P5）**：新增 `tests/` 共 **104 个单元测试**
   （SSRF 防护、Ruffle token、netsec 误报漏报、AdBlock、加解密、历史/下载/配置/地址栏），
   以及 GitHub Actions 工作流（windows-latest 上跑 `pytest` + `ruff`）。
5. **顺带修复**：地址栏输入 `localhost:8000`、`lite:video-check` 不再变成搜索词；
   下载完成后进度显示 100%；解密失败统一抛 `VaultError`。

### 1.6.95

1. **移除 macOS 界面风格**（观感不佳）：界面风格现为 8 种
   （XP / 98 / 7 / 8.1 / 10 / 11 / HarmonyOS / 哈基米）；
   旧配置若保存的是 macOS 会**自动回退到 XP**，不会出现空白界面。
   同时删掉了配套的红黄绿灯圆点绘制与左侧按钮布局代码。
2. **内置无广告 Flash（Ruffle 0.6.0）**，4399 等 Flash 小游戏可玩：
   * 官方 Flash（PPAPI 插件）自 Chromium 88 起被**彻底移除**，无法再集成；
     这里用的是 GitHub 开源项目 **Ruffle**（Rust 编写的 Flash 运行时，
     编译为 WebAssembly），无需插件、**无广告**，
     并以 `polyfills` 伪造 Flash 插件条目，让老站点不再提示"请安装 Flash"；
   * **本地资源供给**：WebView2 的 `WebResourceRequested` 拦截虚拟域名
     `https://ruffle.litebrowser.local/*`，把 `lib/ruffle` 里的文件按 MIME
     返回给网页（含 `application/wasm` 与 CORS 头）；
   * **.swf 代取代理**：自托管 Ruffle 只能抓取带 CORS 头的资源，
     而多数 Flash 站点（如 4399 的 `s7.4399.com`）并不发这些头，
     直接抓会报"被 CORS 策略阻止"。程序在文档创建时先注册一个
     MutationObserver，把 `<embed>/<object>/<param>` 的 swf 地址改写成
     `ruffle.litebrowser.local/proxy?url=...`，由 Python 代取后带回 CORS 头；
     代理只允许 http/https + 以 `.swf` 结尾 + 非内网主机，且仅服务本程序播放页；
   * **.swf 直接播放**：地址栏输入 .swf、命令行传入 .swf（含双击文件关联）
     都会打开内置播放页，而不是把文件下载下来；
   * 开关在「设置 → 网络 → Flash 兼容（Ruffle，无广告）」，默认开启；
   * 实测：4399 的真实 Flash 游戏（`/flash/34111.htm` → `29.swf`，349 KB）
     在**打包版**里正常渲染并可交互。
3. **用户手动标记广告弹窗并屏蔽**：`Ctrl+Shift+A` 进入点选模式
   （红框实时高亮 + 选择器提示），点一下即记录规则并立即隐藏；
   选择器优先取 id、其次取稳定的 class 组合，命中过多时自动收紧；
   规则按域名存于 `adblock.json`，注入 `display:none !important`
   并用 MutationObserver 持续补刀（对付"隐藏后又重新插入"的广告）。
4. **拦截网页自动弹窗**：WebView2 用 `NewWindowRequested.IsUserInitiated`、
   QtWebEngine 用页面焦点判断，非用户点击触发的弹窗直接丢弃，
   状态栏提示本次拦截数量。
5. **Ruffle 体积裁剪与诊断接入**：实测页面只加载
   `core.ruffle.c80159b….js` 与 `826bb093….wasm`，
   已删掉另一套（扩展用）core/wasm 与 sourcemap，从 28 MB 降到 **14.1 MB**；
   「设置 → 内核与环境」与 `--env-report` 现在会报告 Ruffle 版本与体积。
6. **修复命令行/双击打开 .swf 不走内置播放页**的问题（`new_tab` 也应用 .swf 重定向）。
7. 帮助系统更新到 21 个主题，新增「Flash 小游戏（无广告）」「广告与弹窗拦截」。
8. 版本号更新为 **1.6.95**。

### 1.6.91

1. **修复设置页在浅色环境下"黑底 + 深灰字"看不清的问题**（根因修复）：
   当 Windows 处于深色模式时，Qt 的默认调色板本身就是深色的，凡是样式表
   没有显式配色的控件（设置页的滚动区、分组框、提示框等）都会画成 `#1E1E1E` 黑底，
   浅色主题下就成了"黑底深灰字"。现在程序会用**当前主题的调色板**覆盖 Qt 默认调色板
   （`QPalette` 的 Window/Base/Text/Button/Highlight 等角色），
   所有未显式配色的控件底色都会跟随主题；同时把浅色主题的次要文字颜色加深，
   进一步提升对比度。
2. **新增 4 套 UI 风格，共 9 套**：
   * **Windows 11**：扁平标题栏 + 强调色底边、9px 圆角、Mica 风格的浅灰面板；
   * **macOS**：红黄绿三个圆点位于**标题栏左侧**、标题居中、10px 圆角（悬停圆点才显示符号）；
   * **HarmonyOS（鸿蒙）**：白色扁平标题栏 + `#007DFF` 强调线、8px 圆角、浅灰面板；
   * **哈基米（猫猫）**：暖奶油配色、12px 大圆角、标题栏带**猫爪印**图案。
   > 顺带修掉一个布局缺陷：`setFixedSize()` 不会把尺寸策略设为 Fixed，
   > 标题栏按钮会被布局撑开来（macOS 主题下三个圆点散落在标题上），现已修正。
3. **底边栏显示版本号**：状态栏最右侧常显 `v1.6.91`（点击打开「关于」）。
4. **WebView2 环境自动诊断与一键修复**：新增「设置 → 内核与环境」，
   自动检测操作系统与位数、WebView2 运行时（注册表，含用户级安装）、随程序分发的
   组件文件、pythonnet / clr_loader / cffi、.NET 运行时、数据目录可写性，
   逐项显示状态与处理建议；缺运行时可直接**从微软官方下载引导安装器并安装**
   （实测下载 1.76 MB，签名有效），也可复制或保存诊断报告。
5. **深色 / 浅色选择会被记住**：新增「查看 → 深色模式」(`Ctrl+Shift+D`) 快捷切换，
   立即写入配置，下次启动保持上次选择（设置里的切换同样保存）。
6. **命令行环境自检**：`lite browser.exe --env-report` 不打开界面，
   直接做一次环境诊断并把报告写到数据目录的 `env-report.txt`（窗口程序另弹提示框），
   适合网页完全打不开、进不了设置界面时使用。
6. **历史记录搜索高亮**：历史窗口按标题或网址搜索时，
   **命中的关键字以荧光笔底色高亮**，选中行也清晰可读；计数栏会提示已筛选。
7. **下载完成气泡提示**：下载完成后右下角弹出气泡，
   文案为「一只路过的哈基米 🐱 帮你将「文件名」放在了：路径，喵喵。」
   可点 ✕ 关闭；鼠标停在上面时不消失，移开后 2 秒关闭，无人操作则 5 秒自动关闭；
   点气泡本体直接打开所在文件夹（支持多个气泡堆叠）。
8. 帮助系统同步更新到 19 个主题（新增「内核与环境诊断」，并补充视频、下载、
   历史、主题等章节的新特性说明）。
9. 版本号更新为 **1.6.91**。

### 1.6.5

1. **修复后台标签页挂起会打断视频播放的问题**：1.6.0 引入的「后台标签页自动挂起」
   会把正在播放音频/视频的标签页一起挂起，导致切到别的标签页后视频/直播中断。
   现在挂起前会检查 WebView2 的 `IsDocumentPlayingAudio`
   （QtWebEngine 用 `recentlyAudible()`），**正在播放的标签页会自动跳过挂起**，
   手动点「立即挂起后台标签页」也会跳过。
2. **新增「帮助 → 视频播放自检」**：一键打开自检页，直接显示当前渲染引擎、
   WebView2 版本、User-Agent、H.264 / AAC / H.265 / AV1 支持情况、
   MediaSource 与加密媒体支持，并播放一段测试视频；
   若当前内核不支持 H.264（例如 QtWebEngine），页面会给出切换内核的具体步骤。
3. **帮助新增「视频播放（哔哩哔哩等）」章节**，说明常见原因：
   内核选择、番剧/高清需要登录、后台挂起、缓存问题等。
4. **减少不必要的干预**：关闭图片加速时才调用 DevTools 的 `Network.setBlockedURLs`，
   正常浏览时不再启用网络域，避免对视频分片等流式加载产生任何影响。
5. 版本号更新为 **1.6.5**。

### 1.6.1

1. **修复深色模式下设置页文字看不清的问题**：设置页里原先用硬编码灰色写的说明文字
   （例如「数据加密」的状态行、"开启后…"提示行）在深色背景上几乎不可见。
   现在改为由主题样式表驱动的**文字角色**（hint / info / dim / error / warning / heading / card），
   深色浅色自动切换对比度，所有对话框（含查找栏、Cookie 管理器、证书对话框）
   在切换主题时立即重绘，不再残留旧配色。
2. **帮助菜单加入完整功能说明**：新增「帮助 → 使用帮助(F1) / 快捷键一览 / 功能说明 / 常见问题」，
   共 17 个主题，逐项解释每个功能的作用与用法。其中
   **快捷键、UI 风格列表、渲染引擎、搜索引擎、UA 预设等内容直接从程序读取**，
   功能增删后帮助会自动同步，不会过期。
3. **启动速度优化**（实测数据）：
   * **修复首页打开慢/打不开的问题**：程序原先使用 .NET **CoreCLR** 托管 WebView2，
     在打包后的程序里每次启动都要花 **6.4 秒**初始化运行时；
     现已改用 Windows 自带的 **.NET Framework**（保留 CoreCLR 作为回退），
     实测 .NET 初始化 **6.4 秒 → 0.5 秒**，首页打开时间 **约 9 秒 → 约 2.7 秒**；
   * 样式表改为在窗口构造完成后再一次性应用（Qt 只需对控件树做一次 polish），
     主窗口构造耗时 **452 ms → 55 ms**；
   * 状态栏改为单个容器承载，避免 `QStatusBar.addWidget` 每次重新排版并 polish
     （5 次调用约 350 ms）；
   * 新增**启动画面**：进程启动约 **0.19 秒**即可看到界面（首次安装后约 0.2 秒、
     主窗口约 1.2 秒），并且**一直显示到渲染引擎就绪**，不会再出现"空白标签页"；
     状态栏同时显示"正在启动渲染引擎…"；
   * WebView2 环境改为**启动时预热 + 全标签页共享**，多标签共用同一个环境。

   实测启动耗时（打包版，热启动）：启动画面 0.15 s → 主窗口 1.16 s →
   引擎就绪 2.15 s → 首页加载完成 **2.66 s**。

4. **新增桌面快捷方式**：菜单「工具 → 创建桌面快捷方式 / 创建开始菜单快捷方式」，
   便携版用户也能一键生成图标（不依赖安装程序）。

5. **首页地址自动补全**：过去如果在设置里把首页填成 `cn.bing.com`（没有 `https://`），
   保存后下次启动会打不开；现在保存与启动时都会自动补全协议头。

6. **测试数据隔离**：新增 `LITE_BROWSER_DATA_DIR` 环境变量可指定数据目录，
   便于测试或把数据放到任意位置。

### 1.6.0

1. **性能优化**：后台标签页闲置后自动挂起（WebView2 `TrySuspendAsync` /
   QtWebEngine `Frozen` 生命周期），切回标签页自动恢复且不丢页面状态；
   隐藏标签页停止渲染；新增 DNS 预解析、平滑滚动、图片开关、磁盘缓存上限等选项
   （WebView2 通过命令行开关与 DevTools 协议生效）；
   「设置 → 性能」实时显示主进程内存、磁盘缓存、标签页数与挂起数量，并可一键挂起 / 清理缓存。
2. **Cookie 与基础缓存管理**：新增「Cookie 与缓存管理」窗口（`Ctrl+Shift+Del`，
   入口整合在「设置 → 隐私与安全」与「工具」菜单）：列出全部 Cookie
   （域名 / 名称 / 路径 / 安全标记 / 过期时间）并支持关键字筛选、删除所选、删除全部、
   删除会话 Cookie；同时提供清除缓存、清除站点数据（localStorage / IndexedDB）与
   一键清理全部浏览数据，并显示缓存与配置目录的实际占用。
3. **自定义错误页（猫追鼠标）**：网络错误与 HTTP 4xx/5xx 显示自绘错误页，
   页面里的**猫会追着鼠标指针跑**，走路留下脚印，靠近时跳一下；
   同时显示状态码、中文说明与网址，并提供重新加载 / 返回上一页 / 回到主页。
4. **HTTPS 证书校验与恶意网址警告**：证书异常弹出详情对话框由用户决定，
   可开启严格模式直接拒绝；地址栏左侧新增连接安全性指示（挂锁 / 警告）；
   新增恶意网址本地判定引擎（黑白名单 + 启发式规则），命中后显示红色警告页。
5. **网页保存与打印**：支持另存为 **MHTML 单文件** / 完整网页 / 仅 HTML，支持 **打印**
   （WebView2 调起系统打印，QtWebEngine 生成打印预览 PDF）与 **导出 PDF**。
6. **界面自定义**：新增 **Windows 98 / 7 / 8.1 / 10** 四套 UI 风格（与 XP 共五套），
   支持**深色 / 浅色**模式与**自定义边框颜色**，切换立即生效无需重启；
   设置页改为可滚动布局。
7. **User-Agent 可修改**：内置十余种预设（Windows Chrome/Edge/Firefox、macOS Safari、
   Linux、Android、iPhone/iPad、微信），也可完全自定义，实时预览生效值。

### 1.1.0086（分发版）

* 新增 Windows 安装包：单文件安装程序，带安装向导、快捷方式、
  控制面板卸载项与独立卸载程序；支持 `/S` 静默安装与 `/DIR=` 指定目录；
  同时提供免安装便携版压缩包。

### 1.1.0086

1. **新增内置下载模块**：统一下载目录与进度管理，首次下载由用户设定保存目录并记住，
   之后默认使用该目录，可在下载窗口或「设置 → 常规」随时修改，
   也可勾选“每次下载都询问”；支持进度 / 大小 / 状态显示、打开文件与所在文件夹、
   取消、删除、清除已完成，下载记录加密保存。
2. **新增历史记录模块**：按日期分组展示，**每条记录标注打开的日期（含星期）与时间**，
   同一地址自动合并并统计访问次数；支持搜索、双击打开、删除、按时间范围清除、清空全部；
   可在设置中关闭记录或设定保留天数。
3. **新增无痕浏览模式**：工具栏按钮 / `Ctrl+Shift+N` / 设置 → 隐私与安全 三处开关；
   开启后不写入历史，Cookie 与缓存仅存内存（WebView2 InPrivate / QtWebEngine 内存 profile），
   状态栏显示红色标识。
4. **新增数据加密保护**：书签、历史、下载记录改为 **AES-256-GCM** 加密存储，
   主密钥由 Windows DPAPI 保护，并支持设置口令（scrypt）；
   附带解密工具 `tools/decrypt_data.py` 与菜单「工具 → 导出明文数据」，
   旧版明文 JSON 自动迁移。
5. 设置新增「隐私与安全」页，常规页新增下载目录设置；新增「工具」菜单。

### 1.1.0

1. **新增 Edge WebView2 渲染引擎，解决 HTML5 视频无法播放的问题。**
   Qt 官方 QtWebEngine 二进制包不含 H.264/AAC 专有编解码器，
   导致哔哩哔哩等站点提示“不支持 HTML5 播放器”；
   现优先使用系统自带的 Edge WebView2 内核（含完整编解码器），QtWebEngine 作为回退。
2. 新增引擎抽象层（`engine.py` / `wv2engine.py` / `qtengine.py`）。
3. 「设置 → 外观」新增渲染引擎选择；「设置 → 关于」显示引擎与解码能力。
4. 新增 `F12` 开发者工具。

### 1.0.1

1. **修复：必应搜索结果点击后无法打开。**
   Qt6 的 `QWebEnginePage` 已移除 `view()` 方法，导致 `createWindow()` 抛
   `AttributeError` 并返回 `None`，而必应结果页链接恰好都是 `target="_blank"`。
   现改为保存所属视图引用，搜索结果、`window.open()`、右键新标签页均可正常打开。
2. 关于信息中的版权年份改为 **2026**。
3. 新增命令行网址参数。

---

## 十一、使用的开源项目

本项目建立在以下开源项目之上，感谢作者与社区的无私付出：

| 项目 | 用途 | 许可证 | 地址 |
| --- | --- | --- | --- |
| **Ruffle** | 内置的无广告 Flash 运行时（Rust → WebAssembly），让 Flash 内容在现代内核中运行 | MIT / Apache-2.0 | <https://github.com/ruffle-rs/ruffle> |
| **Qt for Python (PySide6)** | 全部界面、窗口、控件与主题绘制 | LGPL-3.0 | <https://github.com/qtproject/pyside-pyside-setup> |
| **Qt WebEngine** | QtWebEngine 渲染内核（回退方案） | LGPL-3.0 | <https://github.com/qt/qtwebengine> |
| **pythonnet** | Python 与 .NET 互操作，用于驱动 Edge WebView2 | MIT | <https://github.com/pythonnet/pythonnet> |
| **clr_loader** | .NET 运行时加载（.NET Framework / .NET） | MIT | <https://github.com/pythonnet/clr-loader> |
| **cryptography** | AES-256-GCM 加密与 scrypt 口令派生 | Apache-2.0 / BSD-3-Clause | <https://github.com/pyca/cryptography> |
| **CFFI** | cryptography 的底层 C 接口 | MIT | <https://github.com/python-cffi/cffi> |
| **PyInstaller** | 打包为单文件可执行程序（开发期工具） | GPL-2.0-or-later（含打包例外） | <https://github.com/pyinstaller/pyinstaller> |
| **Microsoft Edge WebView2** | 系统级 Chromium 渲染运行时与 SDK | 微软软件许可条款 | <https://learn.microsoft.com/microsoft-edge/webview2/> |

补充说明：

* 内置的 Ruffle 以 **MIT / Apache-2.0 双许可**分发，
  其许可证原文随程序一同提供（见 `lib/ruffle/LICENSE_MIT` 与 `lib/ruffle/LICENSE_APACHE`）；
* Qt / PySide6 以 **LGPL-3.0** 分发，本项目以动态链接方式使用，未修改其源码；
* Edge WebView2 运行时是 Windows 10 / 11 的系统组件，
  程序通过其官方 SDK 调用，不随本项目重新分发运行时本体；
* 本项目自身采用 **MIT 许可证**发布（见 [LICENSE](LICENSE)），
  与上述依赖的许可证相互兼容。

## 十二、免责声明

* 本项目仅供学习与个人使用，请遵守当地法律法规与所访问网站的服务条款；
* 内置的广告屏蔽为**用户手动标记**机制，不提供在线规则订阅，也不针对特定网站；
* Flash 兼容依赖第三方开源模拟器 Ruffle，其兼容性由该项目决定，
  本项目不对具体 Flash 内容的可用性作任何保证。

## 十三、许可证

本项目采用 **MIT 许可证**发布：

```
MIT License

Copyright (c) 2026 lvzian

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

第三方组件的许可证见上一章「使用的开源项目」。
