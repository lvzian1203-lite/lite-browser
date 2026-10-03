"""精简 PyInstaller 打包结果，删除用不到的 Qt 组件。

用法：
    python tools/slim_dist.py [dist 目录]

原理：从程序真正加载的 Qt 动态库出发，按 PE 导入表求依赖闭包，
       闭包之外的 ``Qt6*.dll``、无用的 QML 模块和翻译文件会被删除。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

try:
    import pefile
except ImportError:  # pragma: no cover
    pefile = None

# 程序启动时真正会用到的 Qt 库
ROOT_DLLS = [
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "Qt6Network.dll",
    "Qt6PrintSupport.dll",
    "Qt6OpenGL.dll",
    "Qt6OpenGLWidgets.dll",
    "Qt6Quick.dll",
    "Qt6Qml.dll",
    "Qt6QuickWidgets.dll",
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineWidgets.dll",
]

# 可能被运行时动态加载（dlopen），一并保留
EXTRA_KEEP = {
    "qt6positioning.dll",
    "qt6location.dll",
    "qt6svg.dll",
    "qt6webchannel.dll",
    "qt6quickcontrols2.dll",
    "qt6quicktemplates2.dll",
    "qt6quicklayouts.dll",
    "qt6quickcontrols2basic.dll",
    "qt6quickcontrols2fusion.dll",
    "qt6quickcontrols2impl.dll",
    "qt6quickcontrols2basicstyleimpl.dll",
    "qt6quickcontrols2fusionstyleimpl.dll",
    "qt6qmlcore.dll",
    "qt6qmlmodels.dll",
    "qt6qmlmeta.dll",
    "qt6qmlworkerscript.dll",
    "qt6qmllocalstorage.dll",
    "qt6qmlxmllistmodel.dll",
    "qt6qmlnetwork.dll",
    "qt6quickdialogs2.dll",
}

# 保留的翻译（界面语言 + 内核语言包）
KEEP_TRANSLATIONS = {
    "qtbase_zh_CN.qm",
    "qtbase_en.qm",
    "qt_zh_CN.qm",
    "qt_en.qm",
    "qt_help_zh_CN.qm",
    "qt_help_en.qm",
}
KEEP_LOCALES = {"zh-CN.pak", "en-US.pak"}

# 删除的 QML 模块
DROP_QML = {
    "Qt3D",
    "QtCharts",
    "QtDataVisualization",
    "QtGraphs",
    "QtQuick3D",
    "QtTextToSpeech",
    "QtWebSockets",
    "QtWebView",
    "QtVirtualKeyboard",
    "QtMultimedia",
    "QtSensors",
    "QtScxml",
    "QtRemoteObjects",
    "QtNetworkAuth",
    "QtQuick3D",
    "Qt5Compat",
}


def imports_of(path: Path) -> set[str]:
    if pefile is None:
        return set()
    try:
        binary = pefile.PE(str(path), fast_load=True)
        binary.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        names = {
            entry.dll.decode("ascii", "ignore").lower()
            for entry in getattr(binary, "DIRECTORY_ENTRY_IMPORT", [])
        }
        binary.close()
        return names
    except Exception:
        return set()


def dependency_closure(pyside: Path) -> tuple[set[str], dict[str, set[str]]]:
    graph: dict[str, set[str]] = {}
    for dll in pyside.glob("Qt6*.dll"):
        graph[dll.name.lower()] = imports_of(dll)

    keep: set[str] = set()
    queue = [name.lower() for name in ROOT_DLLS if (pyside / name).exists()]
    queue += [name for name in EXTRA_KEEP if (pyside / name).exists()]
    while queue:
        name = queue.pop()
        if name in keep or name not in graph:
            continue
        keep.add(name)
        queue.extend(graph[name] - keep)
    return keep, graph


def human(size: int) -> str:
    return f"{size / 1024 / 1024:.1f} MB"


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dist"
    candidates = [p for p in root.glob("*/_internal") if p.is_dir()]
    if not candidates:
        print(f"未找到打包目录：{root}")
        return 1
    internal = candidates[0]
    pyside = internal / "PySide6"
    if not pyside.is_dir():
        print(f"未找到 PySide6 目录：{pyside}")
        return 1

    if pefile is None:
        print("缺少 pefile，请先执行：pip install pefile")
        return 1

    saved = 0

    # 1) 删除依赖闭包之外的 Qt 动态库
    keep, _graph = dependency_closure(pyside)
    for dll in sorted(pyside.glob("Qt6*.dll")):
        if dll.name.lower() not in keep:
            saved += dll.stat().st_size
            dll.unlink()
            print(f"  删除动态库 {dll.name}")

    # 2) 删除用不到的 QML 模块
    qml = pyside / "qml"
    if qml.is_dir():
        for module in qml.iterdir():
            if module.name in DROP_QML:
                size = sum(f.stat().st_size for f in module.rglob("*") if f.is_file())
                saved += size
                shutil.rmtree(module, ignore_errors=True)
                print(f"  删除 QML 模块 {module.name} ({human(size)})")

    # 3) 删除多余翻译文件
    translations = pyside / "translations"
    if translations.is_dir():
        for item in translations.iterdir():
            if item.is_dir():
                if item.name == "qtwebengine_locales":
                    for pak in item.iterdir():
                        if pak.is_file() and pak.name not in KEEP_LOCALES:
                            saved += pak.stat().st_size
                            pak.unlink()
                continue
            if item.is_file() and item.name not in KEEP_TRANSLATIONS:
                saved += item.stat().st_size
                item.unlink()

    total = sum(f.stat().st_size for f in internal.rglob("*") if f.is_file())
    print(f"\n共释放 {human(saved)}，当前体积 {human(total)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
