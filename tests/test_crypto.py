"""数据加密（DataVault）的单元测试。

覆盖：加解密往返、错误密钥、被篡改的密文、截断密文、原子写入、
缺失主密钥、非法版本号。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from litebrowser import crypto  # noqa: E402
from litebrowser.crypto import CRYPTO_AVAILABLE, DataVault, VaultError  # noqa: E402

MAGIC = b"LTB1"


@unittest.skipUnless(CRYPTO_AVAILABLE, "未安装 cryptography，跳过加密测试")
class CryptoVaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.vault = DataVault(self.root)
        self.assertTrue(self.vault.initialize(), "初始化主密钥应成功")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- 基本往返 ---------------------------------------------------------- #
    def test_encrypt_decrypt_round_trip(self) -> None:
        for payload in (b"", b"hello", "中文内容".encode(), b"x" * 100_000):
            with self.subTest(size=len(payload)):
                blob = self.vault.encrypt(payload)
                self.assertTrue(DataVault.is_encrypted(blob))
                self.assertTrue(blob.startswith(MAGIC), "密文应带版本魔数")
                self.assertEqual(self.vault.decrypt(blob), payload)

    def test_ciphertext_differs_each_time(self) -> None:
        """同一明文两次加密结果必须不同（随机 nonce）。"""
        first = self.vault.encrypt(b"same")
        second = self.vault.encrypt(b"same")
        self.assertNotEqual(first, second)

    def test_write_and_read_text_with_atomic_write(self) -> None:
        blob = self.root / "data" / "bookmarks.dat"
        self.vault.write_text("书签内容", blob)
        self.assertTrue(blob.exists())
        # 原子写入：目录里不应残留临时文件
        leftovers = [p.name for p in blob.parent.iterdir() if p.name.startswith(".tmp")]
        self.assertEqual(leftovers, [], "原子写入不应残留临时文件")
        self.assertEqual(self.vault.read_text(blob), "书签内容")

    # -- 失败路径 ---------------------------------------------------------- #
    def test_wrong_key_fails(self) -> None:
        blob = self.vault.encrypt(b"secret")
        other = DataVault(self.root / "other")
        self.assertTrue(other.initialize())
        with self.assertRaises(VaultError):
            other.decrypt(blob)

    def test_tampered_ciphertext_fails(self) -> None:
        blob = bytearray(self.vault.encrypt(b"secret payload"))
        blob[-1] ^= 0xFF  # 篡改最后一个字节
        with self.assertRaises(VaultError):
            self.vault.decrypt(bytes(blob))

    def test_truncated_ciphertext_fails(self) -> None:
        blob = self.vault.encrypt(b"secret payload")
        for cut in (len(blob) - 1, len(blob) // 2, len(MAGIC) + 1, len(MAGIC)):
            with self.subTest(cut=cut):
                with self.assertRaises(VaultError):
                    self.vault.decrypt(blob[:cut])

    def test_invalid_magic_is_rejected(self) -> None:
        blob = b"XXXX" + self.vault.encrypt(b"data")[len(MAGIC):]
        with self.assertRaises(VaultError):
            self.vault.decrypt(blob)

    def test_plaintext_is_detected_as_not_encrypted(self) -> None:
        self.assertFalse(DataVault.is_encrypted(b'{"bookmarks": []}'))
        self.assertFalse(DataVault.is_encrypted(b""))
        self.assertFalse(DataVault.is_encrypted(b"LTB"))

    def test_missing_master_key_is_reported(self) -> None:
        broken = DataVault(self.root / "broken")
        # 目录存在但没有 master.key：应视为不可用而不是崩溃
        (self.root / "broken").mkdir(parents=True, exist_ok=True)
        self.assertFalse(broken.enabled)
        self.assertEqual(broken.describe(), "未启用")

    def test_legacy_plaintext_migration(self) -> None:
        """旧版明文 JSON 应能被读取（兼容历史数据）。"""
        legacy = self.root / "data" / "bookmarks.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('{"items": []}', encoding="utf-8")
        blob = self.root / "data" / "bookmarks.dat"
        self.assertEqual(self.vault.read_text(blob, legacy), '{"items": []}')

    # -- 口令模式 ---------------------------------------------------------- #
    def test_password_mode_unlock(self) -> None:
        vault = DataVault(self.root / "pw")
        self.assertTrue(vault.initialize())
        vault.set_password("correct horse battery staple")
        self.assertTrue(vault.has_password())

        reopened = DataVault(self.root / "pw")
        self.assertTrue(reopened.available)
        # 口令模式下不能自动解锁
        self.assertFalse(reopened.initialize(), "口令模式下不应自动解锁")
        self.assertTrue(reopened.locked, "读取密钥文件后应处于锁定状态")
        self.assertFalse(reopened.unlock("wrong password"))
        self.assertTrue(reopened.locked, "口令错误后仍应保持锁定")
        self.assertTrue(reopened.unlock("correct horse battery staple"))
        blob = reopened.encrypt(b"after unlock")
        self.assertEqual(reopened.decrypt(blob), b"after unlock")

    def test_clear_password_restores_dpapi_mode(self) -> None:
        vault = DataVault(self.root / "pw2")
        self.assertTrue(vault.initialize())
        vault.set_password("pw")
        vault.clear_password()
        self.assertFalse(vault.has_password())
        reopened = DataVault(self.root / "pw2")
        self.assertTrue(reopened.initialize(), "清除口令后应可用 DPAPI 直接初始化")


class CryptoUnavailableTests(unittest.TestCase):
    """cryptography 缺失时的行为（用打桩模拟，保证 CI 上也能跑）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._real_available = crypto.CRYPTO_AVAILABLE
        self._real_aes = crypto.AESGCM

    def tearDown(self) -> None:
        crypto.CRYPTO_AVAILABLE = self._real_available
        crypto.AESGCM = self._real_aes
        self._tmp.cleanup()

    def test_unavailable_vault_reports_plaintext_mode(self) -> None:
        crypto.CRYPTO_AVAILABLE = False
        crypto.AESGCM = None
        vault = DataVault(Path(self._tmp.name))
        self.assertFalse(vault.available, "缺少加密库时 available 必须为 False")
        self.assertFalse(vault.enabled)
        # 描述里必须明确提到加密库缺失（界面据此提示用户"只能明文保存"）
        self.assertIn("cryptography", vault.describe())

    def test_plaintext_write_is_still_possible_but_explicit(self) -> None:
        """降级为明文时必须能被界面识别（P1-6 要求显式告知，不允许静默）。"""
        crypto.CRYPTO_AVAILABLE = False
        crypto.AESGCM = None
        vault = DataVault(Path(self._tmp.name))
        blob = Path(self._tmp.name) / "data" / "x.dat"
        vault.write_text("plain", blob)
        self.assertEqual(blob.read_text(encoding="utf-8"), "plain")
        self.assertEqual(vault.read_text(blob), "plain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
