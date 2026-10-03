# lite browser test

一款使用 **Python** 编写的轻量浏览器，界面完整仿照 **Windows XP (Luna)** 风格。
本版本为**测试版（1.0.test）**，在稳定版 1.1.0086 的基础上新增了**插件系统**。

渲染引擎支持两种 Chromium 内核，可自动选择：

* **Edge WebView2**（推荐）—— 使用系统自带的 Microsoft Edge 运行时，Chromium 154，
  含 **H.264 / AAC 等完整编解码器**，哔哩哔哩等站点的 HTML5 视频可以正常播放，
  **并支持加载 Chrome 扩展**；
* **QtWebEngine** —— Qt 自带内核，跨平台回退方案（官方二进制包只有开源编解码器，
  不支持 Chrome 扩展，但仍可使用油猴脚本）。

> 作者：**lvzian**　版本：**1.0.test**（测试版）

![主界面](docs/screenshot-main.png)

| 内置下载模块 | 历史记录（按日期分组） |
| --- | --- |
| ![下载](docs/screenshot-downloads.png) | ![历史](docs/screenshot-history.png) |

| 隐私与安全（无痕 / 加密） | 关于 |
| --- | --- |
| ![隐私](docs/screenshot-privacy.png) | ![关于](docs/screenshot-about.png) |


---

## 一、功能特性

| 功能 | 说明 |
| --- | --- |
| Chromium 内核 | 双引擎：Edge WebView2（Chromium 154）/ QtWebEngine（Chromium 122），启动时自动选择，可在设置中切换 |
| **插件系统** | 按 Chrome 扩展规范加载扩展（Manifest V2/V3，支持文件夹 / `.crx` / `.zip` 安装、启用禁用、删除），并内置**油猴脚本**引擎（兼容 Greasemonkey / Tampermonkey 的 `.user.js`），插件管理界面 `Ctrl+Shift+E` |
| 视频播放 | WebView2 引擎下支持 H.264 / AAC / MP3，哔哩哔哩等站点可正常播放 HTML5 视频 |
| **内置下载模块** | `Ctrl+J` 打开下载管理：进度、速度、大小、状态、打开文件 / 所在文件夹、取消、删除；**首次下载时由用户设定保存目录**，之后默认使用该目录，可随时在下载窗口或设置中修改 |
| **历史记录** | `Ctrl+H` 查看，**按日期分组并标注每个页面打开的日期与时间**，支持搜索、双击打开、删除、按时间范围清除、清空全部 |
| **无痕浏览模式** | 设置 → 隐私与安全，或工具栏 / `Ctrl+Shift+N` 一键切换；开启后不写入历史记录，Cookie 与缓存仅存内存（WebView2 使用 InPrivate，QtWebEngine 使用内存 profile），状态栏显示红色“无痕浏览”标识 |
| **数据加密** | 书签 / 历史记录 / 下载记录全部使用 **AES-256-GCM** 加密保存，主密钥由 Windows DPAPI 保护，也可设置口令（scrypt 派生）；附带 **明文导出工具**（菜单「工具 → 导出明文数据」或 `tools/decrypt_data.py`） |
| 仿 WinXP 界面 | 无边框窗口 + Luna 蓝色渐变标题栏、圆角、XP 风格工具栏 / 菜单 / 标签页 / 状态栏 / 滚动条，图标全部由代码绘制 |
| 书签 | 收藏菜单、书签栏、`Ctrl+D` 添加、整理收藏夹（编辑 / 删除 / 排序 / 打开），加密存储 |
| 全屏显示 | `F11` 或菜单「查看 → 全屏显示」，全屏时自动隐藏所有工具栏，`Esc` 退出，也支持网页内 HTML5 全屏 |
| 自定义首页 | 「设置 → 常规」中可自定义主页地址，支持“使用当前页 / 使用默认页 / 使用空白页” |
| 设置 - 关于 | 「设置 → 关于 lite browser」中显示名称、版本、**作者：lvzian**、当前渲染引擎与解码能力 |
| 多标签页 | 新建 / 关闭 / 拖动排序，`+` 按钮新建标签页，`target="_blank"` 自动开新标签页 |
| 地址栏搜索 | 输入关键字自动调用所选搜索引擎（必应 / 百度 / Google / 搜狗 / DuckDuckGo） |
| 其它 | 前进后退、停止刷新、主页、页面内查找(`Ctrl+F`)、缩放、开发者工具(`F12`)、另存为、查看源代码、上次会话恢复、窗口位置记忆 |
| 外部调用 | 支持命令行传入网址：`"lite browser.exe" https://www.example.com` |

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

## 三、插件系统（Chrome 扩展 + 油猴脚本）

按工具栏的「插件」按钮或 `Ctrl+Shift+E` 打开插件管理（「工具 → 插件管理」）。

![插件管理 - 油猴脚本](docs/screenshot-userscripts.png)

### 3.1 Chrome 扩展

遵循 Chrome 扩展规范，直接加载**已解压扩展目录**（内含 `manifest.json`）：

* 支持 **Manifest V2 / V3**，后台 Service Worker、内容脚本、`_locales` 本地化、
  `permissions` / `host_permissions` 解析；
* 安装方式：**从文件夹安装**、**安装 `.crx` / `.zip`**（自动识别 CRX2 / CRX3 头部并取出其中的 zip）；
* 支持启用 / 禁用 / 删除 / 打开扩展目录；
* 扩展运行在 Chromium 的隔离世界中，内容脚本与页面脚本互不干扰（与 Chrome 行为一致）；
* **只有 Edge WebView2 内核支持扩展**；QtWebEngine 内核不支持，界面会给出提示。

扩展目录：`%APPDATA%\LiteBrowserTest\extensions\<扩展 ID>\`

### 3.2 油猴脚本

内置用户脚本引擎，兼容 Greasemonkey / Tampermonkey 的 `.user.js`：

| 元数据 | 支持情况 |
| --- | --- |
| `@name` `@namespace` `@version` `@description` | ✅ |
| `@match` / `@include` / `@exclude` | ✅（Chrome 匹配模式、通配符 `*`、`/正则/`、`<all_urls>`） |
| `@run-at` | ✅ document-start / document-end / document-idle |
| `@grant` | ✅（默认全部提供） |
| `@require` | ✅ 安装时下载并缓存，注入时内联 |

内置 GM API：

| API | 说明 |
| --- | --- |
| `GM_getValue` / `GM_setValue` / `GM_deleteValue` / `GM_listValues` | 数据由宿主持久化，**与其他数据一样 AES-256-GCM 加密存储** |
| `GM_xmlhttpRequest` | **由 Python 宿主代为发起**，不受浏览器同源策略限制（支持 method / headers / data / timeout / onload / onerror） |
| `GM_addStyle` / `GM_log` / `GM_setClipboard` | ✅ |
| `GM_registerMenuCommand` | ✅ 注册的命令出现在「工具 → 用户脚本命令」 |
| `GM_openInTab` | ✅ 在新标签页打开 |
| `GM_notification` / `GM_info` / `unsafeWindow` | ✅ |

安装方式：**安装脚本文件**、**从网址安装**（填写 `.user.js` 链接）、启用 / 禁用 / 详情 / 删除 / 打开脚本目录。

脚本目录：`%APPDATA%\LiteBrowserTest\userscripts\*.user.js`

> 两个内核都支持油猴脚本；QtWebEngine 下 GM 存储会退化为
> `localStorage` 兜底、`GM_xmlhttpRequest` 退化为页面 `fetch`（受同源策略限制）。

### 3.3 自带示例

`samples/` 目录内有可直接使用的示例，用于验证插件接口：

```
samples/extension-demo/          Chrome 扩展（MV3，含 service worker 与内容脚本）
samples/userscript-demo.user.js  油猴脚本示例（GM 存储 / 跨域请求 / 菜单命令）
samples/test-page.html           插件自检页（显示扩展与脚本是否注入成功）
```

在插件管理里分别安装 `extension-demo` 文件夹与 `userscript-demo.user.js`，
然后打开 `samples/test-page.html`，页面会显示两个 ✅。

---

## 四、数据加密与解密工具

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

## 五、目录结构

```
liulanqi/
├─ lite_browser.py          程序入口（源码方式启动）
├─ litebrowser/             程序主体包
│  ├─ main.py               应用初始化（引擎选择、保险库解锁、样式、DPI）
│  ├─ browser.py            浏览器主窗口（标签页、地址栏、书签栏、全屏、菜单）
│  ├─ engine.py             渲染引擎抽象层与工厂
│  ├─ wv2engine.py          Edge WebView2 引擎后端（H.264/AAC）
│  ├─ qtengine.py           QtWebEngine 引擎后端（回退方案）
│  ├─ crypto.py             数据加密：AES-256-GCM + DPAPI / 口令
│  ├─ bookmarks.py          书签存储（加密）
│  ├─ history.py            历史记录（加密，按日期分组）
│  ├─ downloads.py          下载管理（目录规则、进度、记录）
│  ├─ extensions.py         Chrome 扩展接口（manifest 解析、crx/zip 安装）
│  ├─ userscripts.py        油猴脚本引擎（元数据解析、匹配、GM API 与宿主桥接）
│  ├─ plugindialogs.py      插件管理界面
│  ├─ managers.py           下载管理器窗口、历史记录窗口
│  ├─ widgets.py            仿 XP 窗口框架：标题栏、无边框窗口、对话框基类
│  ├─ dialogs.py            设置（常规/外观/隐私与安全/关于）/ 书签对话框
│  ├─ config.py             配置与路径管理
│  ├─ theme.py              XP (Luna) 配色与全局 QSS
│  └─ icons.py              全部图标的代码绘制（无需图片资源）
├─ samples/                 示例 Chrome 扩展 / 油猴脚本 / 插件自检页
├─ lib/webview2/            WebView2 程序集（随程序分发）
├─ tools/
│  ├─ make_icon.py          生成 assets/lite_browser.ico
│  ├─ decrypt_data.py       【解密工具】导出明文 JSON
│  ├─ build_installer.py    构建 Windows 安装包与便携版
│  ├─ installer/            安装程序 / 卸载程序的 C# 源码
│  ├─ slim_dist.py          打包后按依赖关系精简体积
│  └─ version_info.txt      exe 版本信息（公司名 lvzian）
├─ assets/  docs/           图标资源 / 截图与解码自检页
├─ dist/lite browser/       【已打包好的 exe】双击 lite browser.exe 即可运行
├─ run.bat                  源码方式启动
├─ build_exe.bat            一键打包 exe
└─ requirements.txt         依赖：PySide6、pythonnet、cryptography
```

---

## 六、使用方式

### 1. 使用安装包安装

```
lite browser-1.1.0086-安装程序.exe     （141.6 MB）
```

双击运行向导即可安装：

* 纯当前用户安装（默认 `%LOCALAPPDATA%\Programs\lite browser`），**不需要管理员权限**
* 可选创建桌面 / 开始菜单快捷方式，可选安装后运行
* 自动注册到 Windows「已安装的应用 / 程序和功能」，可在其中或开始菜单里卸载
* 卸载时可选择是否一并删除个人数据（默认保留）

![安装向导](docs/screenshot-setup.png)

静默安装（批量部署）：

```bat
"lite browser-1.1.0086-安装程序.exe" /S /DIR="D:\Program Files\lite browser"
rem 可选：/NODESKTOP /NOSTARTMENU /NORUN
```

另有免安装的 `lite browser-1.1.0086-.zip`，解压后双击 `lite browser.exe` 即可使用。

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
build_exe.bat                 rem 打包程序（dist\lite browser）
python tools\build_installer.py --portable   rem 生成安装包与便携版到 D:\dshStar
```

`tools\build_installer.py` 会用系统自带的 C# 编译器（.NET Framework 4.x 的 `csc.exe`）
把 `tools\installer\installer.cs` / `uninstaller.cs` 编译成原生安装程序与卸载程序，
再把程序目录压缩后附加到安装程序 exe 末尾（附加 12 字节尾部标记，供安装程序自读）。

---

## 七、快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl+T` / `Ctrl+W` | 新建 / 关闭标签页 |
| `Ctrl+Shift+E` | 插件管理（Chrome 扩展 / 油猴脚本） |
| `Ctrl+J` | 下载管理 |
| `Ctrl+H` | 历史记录 |
| `Ctrl+Shift+N` | 切换无痕浏览模式 |
| `Ctrl+D` / `Ctrl+Shift+O` | 添加到收藏夹 / 整理收藏夹 |
| `Ctrl+L` / `Ctrl+F` | 定位地址栏 / 页面内查找 |
| `Ctrl+S` / `Ctrl+U` / `F12` | 页面另存为 / 查看源代码 / 开发者工具 |
| `F5` / `Ctrl+R` | 刷新 |
| `F11` | 全屏显示 / 退出全屏 |
| `Esc` | 退出全屏、关闭查找栏 |
| `Ctrl+ +` / `Ctrl+ -` / `Ctrl+0` | 放大 / 缩小 / 实际大小 |
| `Alt+←` / `Alt+→` | 后退 / 前进 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 切换标签页 |
| `Alt+F4` | 退出 |

---

## 八、数据文件位置

| 内容 | 路径 |
| --- | --- |
| 设置 | `%APPDATA%\LiteBrowserTest\settings.json` |
| 书签（加密） | `%APPDATA%\LiteBrowserTest\data\bookmarks.dat` |
| 历史记录（加密） | `%APPDATA%\LiteBrowserTest\data\history.dat` |
| 下载记录（加密） | `%APPDATA%\LiteBrowserTest\data\downloads.dat` |
| 油猴 GM 数据（加密） | `%APPDATA%\LiteBrowserTest\data\userscripts.dat` |
| 主密钥 | `%APPDATA%\LiteBrowserTest\master.key` |
| Chrome 扩展 | `%APPDATA%\LiteBrowserTest\extensions\` |
| 油猴脚本 | `%APPDATA%\LiteBrowserTest\userscripts\` |
| 内核缓存 / Cookies | `%APPDATA%\LiteBrowserTest\profile`、`webview2` |

> 绿色便携模式：在 `lite browser.exe` 同级目录放入一个空的 `portable.txt`，
> 数据就会改为保存在程序目录的 `data` 子文件夹中。
> 旧版本的明文 `bookmarks.json` 会在首次启动时自动加密迁移。

---

## 九、常见问题

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

## 十、关于

- 名称：**lite browser test**
- 版本：**1.0.test**（测试版）
- 作者：**lvzian**
- 界面风格：Windows XP (Luna)
- 版权：Copyright (C) 2026 lvzian

程序内「设置 → 关于 lite browser」中同样可以看到以上信息。

![关于](docs/screenshot-about.png)

---

## 十一、更新记录

### 1.0.test（测试版）

在稳定版 1.1.0086 基础上新增**插件系统**，包名改为 **lite browser test**，
全部文件位于 `lite browser test`。

1. **新增 Chrome 扩展接口**（`extensions.py`）：按 Chrome 扩展规范加载已解压扩展
   （Manifest V2/V3、`_locales` 本地化、权限解析），支持从文件夹 / `.crx` / `.zip` 安装，
   可启用、禁用、删除，并能打开扩展目录；扩展由 Chromium 内核真正加载
   （`CoreWebView2Profile.AddBrowserExtensionAsync`），内容脚本运行在隔离世界。
2. **整合油猴脚本引擎**（`userscripts.py`）：解析 `==UserScript==` 元数据，
   支持 `@match` / `@include` / `@exclude` / `@run-at` / `@grant` / `@require`，
   内置 GM API 兼容层（GM_getValue / GM_setValue / GM_addStyle / GM_xmlhttpRequest /
   GM_openInTab / GM_notification / GM_registerMenuCommand / GM_setClipboard / unsafeWindow / GM_info）；
   GM 数据随其他数据一起加密存储，`GM_xmlhttpRequest` 由宿主 Python 发起，不受同源策略限制。
3. **新增插件管理界面**（`plugindialogs.py`）：Chrome 扩展 / 油猴脚本两个页签，
   工具栏「插件」按钮、菜单「工具 → 插件管理」、快捷键 `Ctrl+Shift+E`；
   用户脚本注册的命令会出现在「工具 → 用户脚本命令」。
4. **新增示例插件**：`samples/extension-demo`（MV3 扩展，含 service worker 与内容脚本）、
   `samples/userscript-demo.user.js`（GM 存储 / 跨域请求 / 菜单命令）、
   `samples/test-page.html`（插件自检页）。
5. 包名、数据目录（`%APPDATA%\LiteBrowserTest`）、窗口标题、exe 名称、
   安装包与卸载项统一改为 **lite browser test**。

### 1.1.0086（分发版）

* 新增 Windows 安装包：单文件安装程序（141.6 MB，压缩自 321.5 MB），
  带安装向导、快捷方式、控制面板卸载项与独立卸载程序；
  支持 `/S` 静默安装与 `/DIR=` 指定目录；同时提供免安装便携版 zip。
  安装包位置：`lite browser-1.1.0086-.exe`

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

Development Note
The skeleton code, calculation module, debug and file management parts of this project are assisted by DeepSeek Harness.
The overall conception, XP-style UI design, function planning, code integration and manual modification are completed independently by the author.
