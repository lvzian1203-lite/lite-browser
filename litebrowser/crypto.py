"""用户数据加密与密钥管理。

* 数据文件使用 **AES-256-GCM** 加密（``.dat``）；
* 主密钥保存在 ``data/master.key``，默认由 **Windows DPAPI** 保护
  （只有同一 Windows 账户才能解密）；
* 也可以在设置中为主密钥设置**口令**（scrypt 派生），便于跨机携带；
* 本模块不依赖 PySide6，因此命令行解密工具可以直接复用。
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import secrets
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

MAGIC = b"LTB1"
FORMAT_VERSION = 1
KEY_SIZE = 32
NONCE_SIZE = 12
SALT_SIZE = 16

try:  # 加密库（缺失时自动退化为明文存储）
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover
    AESGCM = None  # type: ignore
    Scrypt = None  # type: ignore
    CRYPTO_AVAILABLE = False


class VaultError(Exception):
    """加密/解密失败。"""


# --------------------------------------------------------------------------- #
# Windows DPAPI
# --------------------------------------------------------------------------- #
class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def dpapi_available() -> bool:
    return sys.platform == "win32"


def dpapi_protect(data: bytes, entropy: bytes = b"lite browser") -> bytes:
    """用当前 Windows 用户凭据加密（CryptProtectData）。"""
    if not dpapi_available():
        raise VaultError("DPAPI 仅在 Windows 上可用")
    blob_in, keep_in = _blob(data)
    blob_entropy, keep_entropy = _blob(entropy)
    blob_out = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "lite browser data",
        ctypes.byref(blob_entropy),
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise VaultError("CryptProtectData 调用失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        del keep_in, keep_entropy


def dpapi_unprotect(data: bytes, entropy: bytes = b"lite browser") -> bytes:
    """解密 CryptProtectData 的结果。"""
    if not dpapi_available():
        raise VaultError("DPAPI 仅在 Windows 上可用")
    blob_in, keep_in = _blob(data)
    blob_entropy, keep_entropy = _blob(entropy)
    blob_out = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_entropy),
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise VaultError("CryptUnprotectData 调用失败（可能不是同一 Windows 账户）")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        del keep_in, keep_entropy


# --------------------------------------------------------------------------- #
# 保险库
# --------------------------------------------------------------------------- #
def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _derive(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_SIZE, n=2 ** 14, r=8, p=1)
    return kdf.derive(password.encode("utf-8"))


MODE_DPAPI = "dpapi"
MODE_PASSWORD = "password"
MODE_PLAIN = "plain"


class DataVault:
    """管理主密钥，并对数据文件做透明加解密。"""

    def __init__(self, data_dir: Path, key_name: str = "master.key") -> None:
        self.data_dir = Path(data_dir)
        self.key_path = self.data_dir / key_name
        self._key: Optional[bytes] = None
        self._mode = "none"
        self._salt = b""
        self._wrapped = b""
        self._loaded = False

    # -- 状态 ------------------------------------------------------------- #
    @property
    def available(self) -> bool:
        """加密库是否可用。"""
        return CRYPTO_AVAILABLE

    @property
    def enabled(self) -> bool:
        """是否处于加密模式（已解锁且加密库可用）。"""
        return CRYPTO_AVAILABLE and self._key is not None

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def locked(self) -> bool:
        """是否处于“有密钥但需要口令解锁”的状态。"""
        return self._key is None and self._mode == MODE_PASSWORD

    def describe(self) -> str:
        if not CRYPTO_AVAILABLE:
            return "未启用（缺少 cryptography 库）"
        if self._key is None:
            return "已加密（等待口令解锁）" if self.locked else "未启用"
        if self._mode == MODE_PASSWORD:
            return "AES-256-GCM，主密钥由口令保护（scrypt 派生）"
        if self._mode == MODE_DPAPI:
            return "AES-256-GCM，主密钥由 Windows DPAPI 保护"
        return "AES-256-GCM，主密钥以明文保存（非 Windows 环境）"

    # -- 密钥文件 --------------------------------------------------------- #
    def _read_key_file(self) -> bool:
        if self._loaded:
            return True
        self._loaded = True
        if not self.key_path.exists():
            return False
        try:
            payload = json.loads(self.key_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        self._mode = str(payload.get("mode") or "none")
        self._salt = _b64d(payload["salt"]) if payload.get("salt") else b""
        self._wrapped = _b64d(payload.get("data") or "")
        return bool(self._wrapped)

    def _write_key_file(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": FORMAT_VERSION,
            "mode": self._mode,
            "data": _b64e(self._wrapped),
        }
        if self._salt:
            payload["salt"] = _b64e(self._salt)
        tmp = self.key_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.key_path)
        self._loaded = True

    # -- 解锁 ------------------------------------------------------------- #
    def unlock(self, password: Optional[str] = None) -> bool:
        """准备主密钥；口令模式下需要提供正确口令。"""
        if not CRYPTO_AVAILABLE:
            return False
        if self._key is not None:
            return True
        if not self._read_key_file():
            return False

        try:
            if self._mode == MODE_PLAIN:
                self._key = self._wrapped
            elif self._mode == MODE_DPAPI:
                self._key = dpapi_unprotect(self._wrapped)
            elif self._mode == MODE_PASSWORD:
                if not password:
                    return False
                key = _derive(password, self._salt)
                self._key = AESGCM(key).decrypt(self._wrapped[:NONCE_SIZE],
                                                self._wrapped[NONCE_SIZE:], None)
            else:
                return False
        except Exception:
            self._key = None
            return False
        return len(self._key) == KEY_SIZE

    def initialize(self) -> bool:
        """首次运行时生成随机主密钥。"""
        if not CRYPTO_AVAILABLE:
            return False
        if self._key is not None:
            return True
        if self._read_key_file():
            return self.unlock()

        self._key = secrets.token_bytes(KEY_SIZE)
        if dpapi_available():
            try:
                self._wrapped = dpapi_protect(self._key)
                self._mode = MODE_DPAPI
            except VaultError:
                self._wrapped = self._key
                self._mode = MODE_PLAIN
        else:
            self._wrapped = self._key
            self._mode = MODE_PLAIN
        self._write_key_file()
        return True

    # -- 口令 ------------------------------------------------------------- #
    def has_password(self) -> bool:
        if self._mode == MODE_PASSWORD and self._key is None:
            return True
        return self._mode == MODE_PASSWORD

    def set_password(self, password: str) -> None:
        """给主密钥加口令（需要已解锁）。"""
        if self._key is None:
            raise VaultError("主密钥尚未解锁")
        if not password:
            raise VaultError("口令不能为空")
        salt = secrets.token_bytes(SALT_SIZE)
        key = _derive(password, salt)
        nonce = secrets.token_bytes(NONCE_SIZE)
        wrapped = nonce + AESGCM(key).encrypt(nonce, self._key, None)
        self._mode = MODE_PASSWORD
        self._salt = salt
        self._wrapped = wrapped
        self._write_key_file()

    def clear_password(self) -> None:
        """取消口令保护，改回 DPAPI（或明文）。"""
        if self._key is None:
            raise VaultError("主密钥尚未解锁")
        self._salt = b""
        if dpapi_available():
            try:
                self._wrapped = dpapi_protect(self._key)
                self._mode = MODE_DPAPI
            except VaultError:
                self._wrapped = self._key
                self._mode = MODE_PLAIN
        else:
            self._wrapped = self._key
            self._mode = MODE_PLAIN
        self._write_key_file()

    # -- 加解密 ----------------------------------------------------------- #
    def encrypt(self, plaintext: bytes) -> bytes:
        if self._key is None:
            raise VaultError("数据保险库未解锁")
        nonce = secrets.token_bytes(NONCE_SIZE)
        blob = AESGCM(self._key).encrypt(nonce, plaintext, None)
        return MAGIC + bytes([FORMAT_VERSION]) + nonce + blob

    def decrypt(self, blob: bytes) -> bytes:
        """解密数据文件。

        所有失败原因（非本程序数据、版本不符、长度不足、认证标签校验失败）
        统一抛出 :class:`VaultError`，调用方不需要认识底层加密库的异常类型。
        """
        if self._key is None:
            raise VaultError("数据保险库未解锁")
        if not blob.startswith(MAGIC):
            raise VaultError("不是 lite browser 加密数据")
        body = blob[len(MAGIC):]
        if len(body) < 1 + NONCE_SIZE:
            raise VaultError("加密数据不完整（长度不足）")
        version = body[0]
        if version != FORMAT_VERSION:
            raise VaultError(f"不支持的加密格式版本：{version}")
        nonce = body[1:1 + NONCE_SIZE]
        payload = body[1 + NONCE_SIZE:]
        if not payload:
            raise VaultError("加密数据不完整（缺少密文）")
        try:
            return AESGCM(self._key).decrypt(nonce, payload, None)
        except Exception as exc:  # noqa: BLE001 - 统一转成 VaultError，原因记入日志
            log.warning("解密失败（密钥不匹配或数据被篡改）：%s", type(exc).__name__)
            raise VaultError("解密失败：密钥不匹配或数据已损坏") from exc

    @staticmethod
    def is_encrypted(blob: bytes) -> bool:
        return blob.startswith(MAGIC)

    # -- 文件 ------------------------------------------------------------- #
    def read_text(self, blob_path: Path, legacy_path: Optional[Path] = None) -> Optional[str]:
        """读取数据文件（自动兼容旧版明文 JSON，含带 BOM 的文件）。"""
        if blob_path.exists():
            raw = blob_path.read_bytes()
            if self.is_encrypted(raw):
                if self._key is None:
                    return None
                try:
                    return self.decrypt(raw).decode("utf-8-sig")
                except Exception:
                    return None
            try:
                return raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                return None
        if legacy_path is not None and legacy_path.exists():
            try:
                return legacy_path.read_text(encoding="utf-8-sig")
            except OSError:
                return None
        return None

    def write_text(self, text: str, blob_path: Path, legacy_path: Optional[Path] = None) -> None:
        """写入数据文件；加密可用时写密文，否则退回明文。"""
        if self._key is None and self._read_key_file():
            # 密钥存在但尚未解锁：绝不写成明文，避免安全降级
            return
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("utf-8")
        tmp = blob_path.with_suffix(".tmp")
        if self.enabled:
            tmp.write_bytes(self.encrypt(data))
        else:
            tmp.write_bytes(data)
        tmp.replace(blob_path)
        if legacy_path is not None and legacy_path.exists():
            try:
                legacy_path.unlink()
            except OSError:
                pass


__all__ = [
    "CRYPTO_AVAILABLE",
    "DataVault",
    "VaultError",
    "dpapi_available",
    "dpapi_protect",
    "dpapi_unprotect",
    "MODE_DPAPI",
    "MODE_PASSWORD",
    "MODE_PLAIN",
]
