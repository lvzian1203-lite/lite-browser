"""Chrome 扩展（插件）接口。

遵循 Chrome 扩展规范：

* 扩展以「已解压目录」形式安装，目录内必须有 ``manifest.json``；
* 支持 Manifest V2 / V3、``_locales`` 本地化、``permissions`` 解析；
* 支持从文件夹、``.crx``（CRX2 / CRX3）、``.zip`` 安装；
* 真正加载扩展由 Chromium 内核完成（目前只有 Edge WebView2 内核支持），
  QtWebEngine 内核不支持扩展，只提供油猴脚本能力。

扩展目录：``<数据目录>/extensions/<扩展 ID>/``
"""

from __future__ import annotations

import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

#: Chrome 扩展 ID 允许的字符
_ID_RE = re.compile(r"[^a-z0-9]")
#: manifest 中的 __MSG_xxx__ 占位符
_MSG_RE = re.compile(r"__MSG_([A-Za-z0-9_@]+)__")


@dataclass
class Extension:
    """一个已安装的 Chrome 扩展。"""

    id: str
    path: Path
    name: str = ""
    version: str = ""
    description: str = ""
    manifest_version: int = 3
    permissions: list[str] = field(default_factory=list)
    homepage: str = ""
    enabled: bool = True
    error: str = ""
    installed_at: float = field(default_factory=time.time)

    @property
    def display_name(self) -> str:
        return self.name or self.id

    @property
    def permissions_text(self) -> str:
        if not self.permissions:
            return "无"
        text = ", ".join(self.permissions[:6])
        if len(self.permissions) > 6:
            text += f" 等 {len(self.permissions)} 项"
        return text


def read_manifest(folder: Path) -> dict:
    """读取并解析 manifest.json。"""
    path = folder / "manifest.json"
    if not path.exists():
        raise ValueError("目录中没有 manifest.json")
    raw = path.read_text(encoding="utf-8-sig")
    raw = raw.replace("\t", " ").lstrip("\ufeff")
    # 允许 manifest 中出现注释（Chrome 官方不允许，但很多扩展会写）
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("manifest.json 格式不正确")
    return data


def localize(value, folder: Path, default_locale: str = "") -> str:
    """把 __MSG_xxx__ 替换成 _locales 中的文案。"""
    if not isinstance(value, str) or "__MSG_" not in value:
        return value if isinstance(value, str) else str(value)

    locales = folder / "_locales"
    candidates = [default_locale, "zh_CN", "zh", "en", "en_US"]
    for locale in candidates:
        if not locale:
            continue
        messages_file = locales / locale / "messages.json"
        if not messages_file.exists():
            continue
        try:
            messages = json.loads(messages_file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue

        def replace(match: "re.Match") -> str:
            key = match.group(1)
            entry = messages.get(key) or messages.get(key.lower())
            if isinstance(entry, dict) and "message" in entry:
                return str(entry["message"])
            return match.group(0)

        return _MSG_RE.sub(replace, value)
    return _MSG_RE.sub(lambda m: m.group(1), value)


def normalize_id(name: str) -> str:
    """把目录名转成比较像扩展 ID 的形式。"""
    cleaned = _ID_RE.sub("", name.lower())
    return cleaned[:32] or "extension"


class ExtensionStore(QObject):
    """扩展集合。"""

    changed = Signal()

    def __init__(self, config, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.data_dir = Path(data_dir)
        self.directory().mkdir(parents=True, exist_ok=True)
        self._extensions: list[Extension] = []
        self.load()

    # -- 路径 ------------------------------------------------------------- #
    def directory(self) -> Path:
        return self.data_dir / "extensions"

    def _disabled(self) -> set[str]:
        return set(self.config.get("disabled_extensions") or [])

    def _set_disabled(self, values: set[str]) -> None:
        self.config.set("disabled_extensions", sorted(values))

    # -- 扫描 ------------------------------------------------------------- #
    def load(self) -> None:
        disabled = self._disabled()
        found: list[Extension] = []
        root = self.directory()
        for folder in sorted(root.iterdir() if root.is_dir() else []):
            if not folder.is_dir():
                continue
            extension = self._read(folder)
            if extension is not None:
                extension.enabled = extension.id not in disabled
                found.append(extension)
        self._extensions = found

    def _read(self, folder: Path) -> Optional[Extension]:
        extension = Extension(id=folder.name, path=folder)
        try:
            manifest = read_manifest(folder)
        except (OSError, ValueError) as exc:
            extension.error = str(exc)
            extension.name = folder.name
            return extension

        default_locale = str(manifest.get("default_locale") or "")
        extension.name = localize(manifest.get("name", folder.name), folder, default_locale)
        extension.version = str(manifest.get("version") or "")
        extension.description = localize(
            manifest.get("description", ""), folder, default_locale
        )
        try:
            extension.manifest_version = int(manifest.get("manifest_version") or 3)
        except (TypeError, ValueError):
            extension.manifest_version = 3

        permissions = list(manifest.get("permissions") or [])
        permissions += list(manifest.get("host_permissions") or [])
        if manifest.get("optional_permissions"):
            permissions += [f"{item}（可选）" for item in manifest["optional_permissions"]]
        extension.permissions = [str(item) for item in permissions]
        extension.homepage = str(manifest.get("homepage_url") or "")
        return extension

    # -- 查询 ------------------------------------------------------------- #
    def all(self) -> list[Extension]:
        return list(self._extensions)

    def count(self) -> int:
        return len(self._extensions)

    def at(self, ext_id: str) -> Optional[Extension]:
        for extension in self._extensions:
            if extension.id == ext_id:
                return extension
        return None

    def enabled(self) -> list[Extension]:
        return [item for item in self._extensions if item.enabled and not item.error]

    # -- 安装 ------------------------------------------------------------- #
    def install_folder(self, source: Path) -> Extension:
        """从文件夹安装（复制到扩展目录）。"""
        source = Path(source)
        if not (source / "manifest.json").exists():
            raise ValueError("所选目录不是 Chrome 扩展（缺少 manifest.json）")
        try:
            manifest = read_manifest(source)
        except ValueError as exc:
            raise ValueError(f"manifest.json 解析失败：{exc}")

        base = normalize_id(str(manifest.get("name") or source.name))
        target = self.directory() / base
        index = 1
        while target.exists():
            target = self.directory() / f"{base}{index}"
            index += 1
        shutil.copytree(source, target)

        extension = self._read(target)
        if extension is None:
            raise ValueError("安装失败")
        self._extensions.append(extension)
        self.changed.emit()
        return extension

    def install_archive(self, archive: Path) -> Extension:
        """从 .crx / .zip 安装。"""
        archive = Path(archive)
        data = archive.read_bytes()
        offset = 0
        if data[:4] == b"Cr24":
            version = int.from_bytes(data[4:8], "little")
            if version == 2:
                key_len = int.from_bytes(data[8:12], "little")
                sig_len = int.from_bytes(data[12:16], "little")
                offset = 16 + key_len + sig_len
            elif version == 3:
                header_len = int.from_bytes(data[8:12], "little")
                offset = 12 + header_len
            else:
                raise ValueError(f"不支持的 CRX 版本：{version}")

        import io

        try:
            with zipfile.ZipFile(io.BytesIO(data[offset:])) as bundle:
                names = bundle.namelist()
                if "manifest.json" not in names:
                    # 有些包会把扩展放在一级子目录里
                    roots = {name.split("/")[0] for name in names if "/" in name}
                    if len(roots) == 1 and f"{roots.pop()}/manifest.json" in names:
                        offset_name = names[0].split("/")[0] + "/"
                    else:
                        raise ValueError("压缩包中没有 manifest.json")
                else:
                    offset_name = ""

                temp = self.directory() / f".install-{int(time.time())}"
                if temp.exists():
                    shutil.rmtree(temp, ignore_errors=True)
                temp.mkdir(parents=True)
                for name in names:
                    if offset_name and not name.startswith(offset_name):
                        continue
                    relative = name[len(offset_name):]
                    if not relative:
                        continue
                    target = temp / relative
                    if name.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(name) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"无法解压：{exc}")

        try:
            extension = self.install_folder(temp)
        finally:
            shutil.rmtree(temp, ignore_errors=True)
        return extension

    def install(self, source: Path) -> Extension:
        source = Path(source)
        if source.is_dir():
            return self.install_folder(source)
        if source.suffix.lower() in (".crx", ".zip"):
            return self.install_archive(source)
        raise ValueError("请选择扩展文件夹、.crx 或 .zip 文件")

    # -- 管理 ------------------------------------------------------------- #
    def set_enabled(self, ext_id: str, enabled: bool) -> None:
        disabled = self._disabled()
        if enabled:
            disabled.discard(ext_id)
        else:
            disabled.add(ext_id)
        self._set_disabled(disabled)
        extension = self.at(ext_id)
        if extension is not None:
            extension.enabled = enabled
        self.changed.emit()

    def remove(self, ext_id: str) -> bool:
        extension = self.at(ext_id)
        if extension is None:
            return False
        shutil.rmtree(extension.path, ignore_errors=True)
        self._extensions = [item for item in self._extensions if item.id != ext_id]
        disabled = self._disabled()
        disabled.discard(ext_id)
        self._set_disabled(disabled)
        self.changed.emit()
        return True

    def reload(self) -> None:
        self.load()
        self.changed.emit()
