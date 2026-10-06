"""广告屏蔽（规则存储 + 注入脚本）的单元测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from litebrowser import adblock  # noqa: E402


class AdRuleStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "adblock.json"
        self.store = adblock.AdRuleStore(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_add_and_match_same_domain(self) -> None:
        rule = self.store.add("https://www.4399.com/game/1.htm", "#ad-banner")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.domain, "4399.com", "www. 前缀应被归一")
        self.assertEqual(self.store.selectors_for("https://www.4399.com/x"), ["#ad-banner"])

    def test_rule_does_not_leak_to_other_domains(self) -> None:
        self.store.add("4399.com", ".ad")
        self.assertEqual(self.store.selectors_for("https://other.com/"), [])

    def test_wildcard_domain_matching(self) -> None:
        self.store.add("*.example.com", "#promo")
        self.assertEqual(self.store.selectors_for("https://a.example.com/"), ["#promo"])
        self.assertEqual(self.store.selectors_for("https://example.com/"), ["#promo"])
        self.assertEqual(self.store.selectors_for("https://notexample.com/"), [])

    def test_duplicate_rule_is_not_added_twice(self) -> None:
        self.store.add("example.com", ".ad")
        self.store.add("example.com", ".ad")
        self.assertEqual(len(self.store.rules), 1)

    def test_persistence_round_trip(self) -> None:
        self.store.add("example.com", "#one", note="测试")
        self.store.set_block_popups(False)
        reloaded = adblock.AdRuleStore(self.path)
        self.assertEqual(len(reloaded.rules), 1)
        self.assertEqual(reloaded.rules[0].selector, "#one")
        self.assertFalse(reloaded.block_popups)

    def test_corrupted_file_does_not_crash(self) -> None:
        self.path.write_text("{ this is not json", encoding="utf-8")
        store = adblock.AdRuleStore(self.path)
        self.assertEqual(store.rules, [])

    def test_remove_and_clear(self) -> None:
        rule = self.store.add("example.com", ".ad")
        self.assertTrue(self.store.remove(rule))
        self.assertEqual(self.store.rules, [])
        self.store.add("a.com", ".a")
        self.store.add("b.com", ".b")
        self.store.clear()
        self.assertEqual(self.store.rules, [])

    def test_empty_selector_is_rejected(self) -> None:
        self.assertIsNone(self.store.add("example.com", "   "))

    def test_local_file_domain(self) -> None:
        rule = self.store.add("file:///C:/x/page.html", "#ad")
        self.assertEqual(rule.domain, "本地文件")

    def test_selector_is_truncated(self) -> None:
        rule = self.store.add("example.com", "#" + "a" * 1000)
        self.assertLessEqual(len(rule.selector), adblock.MAX_SELECTOR)


class InjectScriptTests(unittest.TestCase):
    def test_empty_rules_is_noop(self) -> None:
        self.assertEqual(adblock.apply_script([]), "void 0")

    def test_script_hides_selectors(self) -> None:
        script = adblock.apply_script(["#ad-banner", ".popup"])
        self.assertIn("#ad-banner", script)
        self.assertIn("display:none !important", script)

    def test_script_batches_mutations(self) -> None:
        """P1-3：注入脚本必须用 requestAnimationFrame + 脏标记批处理。"""
        script = adblock.apply_script([".ad"])
        self.assertIn("requestAnimationFrame", script)
        self.assertIn("pending", script)
        self.assertIn("__lite_adblock_cache", script, "应缓存样式内容避免重复写 DOM")

    def test_script_keeps_dynamic_content_support(self) -> None:
        script = adblock.apply_script([".ad"])
        self.assertIn("MutationObserver", script)
        self.assertIn("childList: true", script, "动态插入的广告仍需被隐藏")

    def test_rules_are_embedded_as_json(self) -> None:
        script = adblock.apply_script(['.a"b', "#x"])
        payload = script.split("var selectors = ", 1)[1].split(";", 1)[0]
        self.assertEqual(json.loads(payload), ['.a"b', "#x"])

    def test_picker_has_postmessage_and_fallback(self) -> None:
        script = adblock.picker_script()
        self.assertIn("chrome.webview.postMessage", script)
        self.assertIn("lite:adpick?", script, "QtWebEngine 需要内部命令回退路径")
        self.assertIn("Escape", script)

    def test_parse_pick_command_round_trip(self) -> None:
        from urllib.parse import quote

        selector = "#ad-banner > .inner"
        url = ("lite:adpick?selector=" + quote(selector, safe="")
               + "&host=" + quote("www.4399.com", safe=""))
        parsed_selector, host = adblock.parse_pick_command(url)
        self.assertEqual(parsed_selector, selector)
        self.assertEqual(host, "www.4399.com")

    def test_parse_pick_command_tolerates_garbage(self) -> None:
        self.assertEqual(adblock.parse_pick_command("lite:adpick"), ("", ""))
        self.assertEqual(adblock.parse_pick_command(""), ("", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
