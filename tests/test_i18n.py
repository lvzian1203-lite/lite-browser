"""多语言（i18n）测试：语言切换、占位符、短语替换，以及**翻译覆盖率**。

其中"覆盖率"是这套机制的关键保障：界面代码里的每一处 ``tr("…")`` /
``trf("…")`` 都必须在英文翻译表里有对应条目，否则英文界面会夹着中文。
"""

from __future__ import annotations

import ast
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from litebrowser import i18n  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")

#: 有意不翻译的字符串（数据/文件格式内容，不是界面文字）
ALLOW_ZH = {
    "# lite browser 网址黑名单（每行一个域名，# 注释，! 表示白名单）",
}


def _restore_language():
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


class LanguageSwitchingTests(unittest.TestCase):
    def setUp(self) -> None:
        _restore_language()

    def tearDown(self) -> None:
        _restore_language()

    def test_supported_languages(self) -> None:
        codes = [code for code, _ in i18n.available_languages()]
        self.assertEqual(codes, ["zh_CN", "en"])
        names = [name for _, name in i18n.available_languages()]
        self.assertIn("English", names)
        self.assertTrue(any("中文" in name for name in names))

    def test_normalize_language(self) -> None:
        for text in ("en", "EN", "en-US", "English", "eng"):
            self.assertEqual(i18n.normalize_language(text), "en", text)
        for text in ("zh", "zh-CN", "zh_CN", "中文", "简体中文", None, ""):
            self.assertEqual(i18n.normalize_language(text), "zh_CN", str(text))
        self.assertEqual(i18n.normalize_language("nonsense"), i18n.DEFAULT_LANGUAGE)

    def test_chinese_mode_returns_source(self) -> None:
        i18n.set_language("zh_CN")
        for text in ("后退", "设置", "隐私与安全"):
            self.assertEqual(i18n.tr(text), text)
        self.assertFalse(i18n.is_english())

    def test_english_mode_translates_known_strings(self) -> None:
        i18n.set_language("en")
        self.assertTrue(i18n.is_english())
        self.assertEqual(i18n.tr("后退"), "Back")
        self.assertEqual(i18n.tr("前进"), "Forward")
        self.assertEqual(i18n.tr("设置"), "Settings")

    def test_unknown_string_falls_back_to_chinese(self) -> None:
        i18n.set_language("en")
        unknown = "这段文字还没有翻译"
        self.assertEqual(i18n.tr(unknown), unknown)

    def test_empty_string_is_safe(self) -> None:
        i18n.set_language("en")
        self.assertEqual(i18n.tr(""), "")


class PlaceholderTests(unittest.TestCase):
    def setUp(self) -> None:
        _restore_language()

    def tearDown(self) -> None:
        _restore_language()

    def test_trf_in_chinese_mode(self) -> None:
        i18n.set_language("zh_CN")
        self.assertEqual(i18n.trf("共 {0} 个文件", 3), "共 3 个文件")

    def test_trf_uses_english_template(self) -> None:
        i18n.set_language("en")
        i18n.load_catalog({**i18n.catalog(), "共 {0} 个文件": "{0} files in total"})
        self.assertEqual(i18n.trf("共 {0} 个文件", 3), "3 files in total")

    def test_trf_bad_template_does_not_crash(self) -> None:
        """译文占位符写错时要退回中文模板而不是崩溃。"""
        i18n.set_language("en")
        i18n.load_catalog({**i18n.catalog(), "共 {0} 个文件": "{1} files"})
        result = i18n.trf("共 {0} 个文件", 3)
        self.assertIn("3", result, "至少要把参数填进去，不能抛异常")

    def test_trf_without_args(self) -> None:
        i18n.set_language("en")
        i18n.load_catalog({**i18n.catalog(), "确定": "OK"})
        self.assertEqual(i18n.trf("确定"), "OK")


class LongTextTests(unittest.TestCase):
    def setUp(self) -> None:
        _restore_language()

    def tearDown(self) -> None:
        _restore_language()

    def test_tr_html_replaces_phrase_keeps_tags(self) -> None:
        i18n.set_language("en")
        html = "<div><button>返回上一页</button></div>"
        result = i18n.tr_html(html)
        self.assertIn("Go back", result)
        self.assertIn("<div>", result)
        self.assertIn("<button>", result)
        self.assertNotIn("返回上一页", result)

    def test_tr_html_leaves_unknown_text(self) -> None:
        i18n.set_language("en")
        html = "<p>这句话没有译文</p>"
        self.assertEqual(i18n.tr_html(html), html)

    def test_tr_html_noop_in_chinese(self) -> None:
        i18n.set_language("zh_CN")
        html = "<p>返回上一页</p>"
        self.assertEqual(i18n.tr_html(html), html)

    def test_tr_text_translates_whole_lines(self) -> None:
        i18n.set_language("en")
        i18n.load_catalog({**i18n.catalog(), "第一行中文": "First line"})
        text = "第一行中文\n这行没有译文\n"
        result = i18n.tr_text(text)
        self.assertIn("First line", result)
        self.assertIn("这行没有译文", result)

    def test_tr_text_preserves_indentation(self) -> None:
        i18n.set_language("en")
        i18n.load_catalog({**i18n.catalog(), "缩进行": "Indented line"})
        self.assertEqual(i18n.tr_text("     缩进行"), "     Indented line")


class CatalogCoverageTests(unittest.TestCase):
    """界面代码里的每一条 tr()/trf() 都必须真的能被翻译成英文。"""

    @classmethod
    def setUpClass(cls) -> None:
        i18n.set_language("en")
        cls.catalog = i18n.catalog()
        cls.missing: list[tuple[str, int, str]] = []
        cls.literals: set[str] = set()
        for path in sorted((ROOT / "litebrowser").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", "")
                if name not in ("tr", "trf") or not node.args:
                    continue
                first = node.args[0]
                if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                    continue
                value = first.value
                if not CJK.search(value):
                    continue
                cls.literals.add(value)
                if value in ALLOW_ZH:
                    continue
                # 用运行时的真实查找判定：tr() 必须真的改变它
                if i18n.tr(value) == value:
                    cls.missing.append((path.name, node.lineno, value))
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_every_wrapped_string_has_translation(self) -> None:
        details = "\n".join(
            f"  {name}:{line}: {text[:70]!r}" for name, line, text in self.missing[:40]
        )
        self.assertEqual(
            self.missing, [],
            f"有 {len(self.missing)} 条界面文字翻译后在英文下仍是中文：\n{details}",
        )

    def test_catalog_is_not_empty(self) -> None:
        self.assertGreater(len(self.catalog), 300)

    def test_catalog_values_are_english(self) -> None:
        """译文里不应残留中文（专有名词除外）。"""
        suspicious = {
            key: value
            for key, value in self.catalog.items()
            if CJK.search(value) and "lite browser" not in value
        }
        self.assertEqual(
            suspicious, {},
            f"这些译文里仍有中文：{list(suspicious.items())[:5]}",
        )

    def test_no_duplicate_keys_possible(self) -> None:
        """字典天然去重；这里确认没有空键或空值。"""
        for key, value in self.catalog.items():
            self.assertTrue(key.strip(), "不允许空键")
            self.assertTrue(str(value).strip(), f"{key!r} 的译文为空")


class NoChineseLeakTests(unittest.TestCase):
    """英文模式下，长文本也必须真的没有中文残留。

    回归背景：实测出现过三类中英混排——
    1. 长 f-string 插值后整行与译文键不一致（"7 种 UI 风格：「Settings …」"）；
    2. 短语替换把中文句子切碎（"直接使用 IP Address访问"）；
    3. **模块级 tr() 在导入期执行**，而那时还没读到 ui_language，
       于是 UA 预设名之类永久固定在中文。

    第 3 类必须在"先定语言、再导入界面模块"的顺序下才能复现，
    所以这里用子进程模拟真实启动顺序（进程内 pytest 早已导入过这些模块）。
    """

    #: 允许保留的中文：示例数据（站点名、示例网址）
    ALLOW = ("example.com", "litebrowser.local", "example.org")

    CHECK_SCRIPT = r"""
import os, re, sys, json, tempfile, pathlib

root = tempfile.mkdtemp(prefix="lite-leak-")
os.environ["LITE_BROWSER_DATA_DIR"] = root
pathlib.Path(root, "settings.json").write_text(
    json.dumps({"ui_language": "en"}), encoding="utf-8"
)

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from litebrowser.config import Config
from litebrowser.i18n import apply_language_from_config, tr, tr_text

config = Config()
apply_language_from_config(config)          # 真实启动顺序：先定语言

import litebrowser.help as helpmod          # 再导入界面模块
from litebrowser.errors import error_page, warning_page
from litebrowser.netsec import SecurityManager

CJK = re.compile(r"[\u4e00-\u9fff]")
ALLOW = ("example.com", "litebrowser.local", "example.org")
leaks = []

for topic in helpmod.sections():
    for label, rendered in (("title", tr(topic.title)), ("body", tr_text(topic.body))):
        for line in rendered.splitlines():
            if CJK.search(line) and not any(a in line for a in ALLOW):
                leaks.append(f"{topic.key}/{label}: " + re.sub(r"<[^>]+>", "", line).strip()[:70])

class _Cfg:
    def get(self, key, default=None):
        return {"block_malicious": True}.get(key, default)
    def set(self, key, value, save=True):
        return None

verdict = SecurityManager(_Cfg(), pathlib.Path(root)).check_url("http://93.184.216.34/")
pages = {
    "error_page": error_page("https://example.com/x", 404, "Not Found"),
    "warning_page": warning_page("http://93.184.216.34/", list(verdict.reasons)),
}
for name, html in pages.items():
    body = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    body = re.sub(r"<script>.*?</script>", "", body, flags=re.S)
    body = re.sub(r"<[^>]+>", "", body)
    for line in body.splitlines():
        if CJK.search(line) and not any(a in line for a in ALLOW):
            leaks.append(f"{name}: {line.strip()[:70]}")

print("LEAKS=" + str(len(leaks)))
for item in leaks[:20]:
    print("  " + item)
"""

    def test_no_chinese_leak_in_real_startup_order(self) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-c", self.CHECK_SCRIPT],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0,
                         f"子进程检查失败：{result.stderr[-400:]}")
        self.assertIn("LEAKS=0", result.stdout,
                      f"英文界面里仍有中文：\n{result.stdout[-800:]}")

    def test_no_translation_value_contains_chinese(self) -> None:
        bad = {key: value for key, value in i18n.catalog().items() if CJK.search(value or "")}
        self.assertEqual(bad, {}, f"译文里不应含中文：{list(bad.items())[:5]}")


class DataNotTranslatedTests(unittest.TestCase):
    """写进用户数据文件的文字**不能**跟着界面语言变。

    回归背景：自动包装工具曾把 ``blocklist.txt`` 的文件头也包成 ``tr(...)``。
    虽然当时译文表里映射为原文、没出问题，但这是隐患：
    一旦补上译文，英文界面就会把用户数据文件写成英文，破坏既有数据形态。
    """

    HEADER = "# lite browser 网址黑名单（每行一个域名，# 注释，! 表示白名单）"

    def setUp(self) -> None:
        i18n.set_language("en")      # 故意用英文环境

    def tearDown(self) -> None:
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_blocklist_header_stays_chinese(self) -> None:
        import tempfile

        from litebrowser.netsec import SecurityManager

        class _Config:
            def get(self, key, default=None):
                return {"block_malicious": True}.get(key, default)

            def set(self, key, value, save=True):  # noqa: A003
                return None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = SecurityManager(_Config(), root)
            manager._write_default_list()
            manager.add_blocked("ads.example.com")
            first = (root / "blocklist.txt").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first, self.HEADER,
                         "英文环境下 blocklist.txt 的文件头也必须保持中文原文")

    def test_source_does_not_translate_file_content(self) -> None:
        """静态检查：写文件的那行不允许出现 tr()。"""
        path = ROOT / "litebrowser" / "netsec.py"
        source = path.read_text(encoding="utf-8")
        offenders = [
            line.strip()
            for line in source.splitlines()
            if "网址黑名单（每行一个域名" in line and "tr(" in line
        ]
        self.assertEqual(offenders, [], f"数据文件内容被包进了 tr()：{offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
