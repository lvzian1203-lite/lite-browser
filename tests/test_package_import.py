"""包导入与「无 PySide6 环境」可用性测试。

回归背景：``litebrowser/__init__.py`` 原先 ``from .config import ...``，
而 ``config`` 依赖 ``PySide6.QtCore``；于是只要导入本包的**任何**子模块
都会拉起 Qt。``tools/decrypt_data.py`` 是数据恢复工具（用户浏览器坏掉时
才会用），当时在未安装 PySide6 的机器上直接 ``ModuleNotFoundError`` 崩溃。

本测试用 ``sys.meta_path`` 拦截器在**子进程**里屏蔽 PySide6，
验证纯 Python 路径（version / crypto / 解密工具）确实不依赖 Qt。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

BLOCKER = """
import sys
from importlib.abc import MetaPathFinder


class _Blocker(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.', 1)[0] in ('PySide6', 'shiboken6'):
            raise ImportError('No module named %r (blocked for test)' % fullname)
        return None


sys.meta_path.insert(0, _Blocker())
sys.path.insert(0, r'{root}')
"""


def run_without_qt(body: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """在屏蔽 PySide6 的子进程里执行 Python 代码。"""
    code = BLOCKER.format(root=str(ROOT)) + body
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd or ROOT),
    )


class NoQtImportTests(unittest.TestCase):
    def test_blocker_actually_blocks_qt(self) -> None:
        """前置检查：拦截器必须真的能挡住 PySide6，否则下面的用例没有意义。"""
        result = run_without_qt("import PySide6")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("blocked", result.stderr)

    def test_version_module_has_no_qt_dependency(self) -> None:
        result = run_without_qt(
            "from litebrowser.version import APP_NAME, APP_VERSION, AUTHOR\n"
            "print(APP_NAME, APP_VERSION, AUTHOR)"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("lite browser", result.stdout)

    def test_package_constants_available_without_qt(self) -> None:
        result = run_without_qt(
            "import litebrowser\n"
            "print(litebrowser.APP_NAME, litebrowser.APP_VERSION, litebrowser.__author__)\n"
            "from litebrowser import APP_NAME, APP_VERSION, AUTHOR\n"
            "assert AUTHOR == 'lvzian'\n"
            "print('ok')"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("lite browser", result.stdout)
        self.assertIn("ok", result.stdout)

    def test_crypto_imports_without_qt(self) -> None:
        result = run_without_qt(
            "from litebrowser.crypto import DataVault, VaultError, CRYPTO_AVAILABLE\n"
            "print('crypto ok', CRYPTO_AVAILABLE)"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("crypto ok", result.stdout)

    def test_safefetch_imports_without_qt(self) -> None:
        """SSRF 防护模块本身也不应依赖 Qt。"""
        result = run_without_qt(
            "from litebrowser.safefetch import address_is_public, MAX_REDIRECTS\n"
            "print('safefetch ok', MAX_REDIRECTS)"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("safefetch ok", result.stdout)

    def test_unknown_attribute_still_raises(self) -> None:
        result = run_without_qt(
            "import litebrowser\n"
            "try:\n"
            "    litebrowser.NO_SUCH_NAME\n"
            "except AttributeError as exc:\n"
            "    print('attrerror ok', exc)\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("attrerror ok", result.stdout)

    def test_dir_lists_public_constants(self) -> None:
        result = run_without_qt(
            "import litebrowser\n"
            "names = dir(litebrowser)\n"
            "assert 'APP_NAME' in names and 'APP_VERSION' in names and 'AUTHOR' in names\n"
            "print('dir ok')"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dir ok", result.stdout)


class DecryptToolWithoutQtTests(unittest.TestCase):
    """解密工具在无 Qt 环境下必须可用（用户的数据恢复路径）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_data_dir(self) -> Path:
        """用程序自身的存储类生成一份加密数据（需要 Qt，故在主进程执行）。

        目录布局与程序一致：``<数据目录>/master.key`` + ``<数据目录>/data/*.dat``。
        """
        from litebrowser.bookmarks import BookmarkStore
        from litebrowser.crypto import DataVault
        from litebrowser.history import HistoryStore

        data_dir = self.root
        (data_dir / "data").mkdir(parents=True, exist_ok=True)
        vault = DataVault(data_dir)
        self.assertTrue(vault.initialize(), "初始化主密钥失败")

        bookmarks = BookmarkStore(vault, data_dir)
        bookmarks.add("示例站点", "https://example.com/")
        history = HistoryStore(vault, data_dir)
        history.record("https://example.com/", "示例站点")
        # 用 save() 立即落盘（不依赖 v1.7.1 才引入的合并写盘 / flush_now）
        history.save()

        self.assertTrue((data_dir / "data" / "bookmarks.dat").exists(),
                        "书签应写入 <数据目录>/data/bookmarks.dat")
        self.assertTrue((data_dir / "data" / "history.dat").exists(),
                        "历史应写入 <数据目录>/data/history.dat")
        return data_dir

    def test_list_and_export_without_qt(self) -> None:
        """在真正屏蔽 PySide6 的子进程里跑解密工具：--list 与导出都要成功。"""
        data = self._make_data_dir()
        out = self.root / "export"
        tool = str(ROOT / "tools" / "decrypt_data.py")

        list_result = subprocess.run(
            [sys.executable, "-c",
             BLOCKER.format(root=str(ROOT))
             + f"import runpy, sys\nsys.argv = ['decrypt_data.py', '--data-dir', r'{data}', '--list']\n"
               f"runpy.run_path(r'{tool}', run_name='__main__')"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
        )
        self.assertEqual(list_result.returncode, 0,
                         f"无 PySide6 时 --list 失败：{list_result.stderr}")
        self.assertIn("加密状态", list_result.stdout)

        export_result = subprocess.run(
            [sys.executable, "-c",
             BLOCKER.format(root=str(ROOT))
             + f"import runpy, sys\nsys.argv = ['decrypt_data.py', '--data-dir', r'{data}',"
               f" '--out', r'{out}']\n"
               f"runpy.run_path(r'{tool}', run_name='__main__')"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
        )
        self.assertEqual(export_result.returncode, 0,
                         f"无 PySide6 时导出失败：{export_result.stderr}")

        exported = sorted(p.name for p in out.glob("*.json"))
        self.assertIn("bookmarks.json", exported)
        self.assertIn("history.json", exported)
        payload = json.loads((out / "bookmarks.json").read_text(encoding="utf-8"))
        self.assertIn("example.com", json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
