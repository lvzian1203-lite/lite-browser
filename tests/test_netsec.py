"""netsec（可疑网址启发式规则）的单元测试。

要点：
* 正常站点不能被误报（false positive）；
* 典型可疑 URL 必须命中（false negative 统计）；
* 判定语义是"启发式"，不是恶意网址库——相关文案由 :data:`netsec.DISCLAIMER` 提供。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from litebrowser import netsec  # noqa: E402
from litebrowser.netsec import DANGER, OK, SecurityManager, WARN  # noqa: E402

_app = QCoreApplication.instance() or QCoreApplication(sys.argv)


class _FakeConfig:
    """SecurityManager 只用到 config 的少量键，这里给一个最小替身。"""

    def __init__(self) -> None:
        self._data = {"block_malicious": True}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value, save=True):  # noqa: A003
        self._data[key] = value


class NetsecTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.manager = SecurityManager(_FakeConfig(), Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _verdict(self, url: str):
        return self.manager.check_url(url)

    # -- 正常站点不应误报 -------------------------------------------------- #
    def test_normal_sites_are_not_flagged(self) -> None:
        normal = [
            "https://github.com/ruffle-rs/ruffle",
            "https://github.com/lvzian1203-lite/lite-browser",
            "https://www.google.com/search?q=flash",
            "https://zh.wikipedia.org/wiki/Flash",
            "https://example.com/",
            "https://cn.bing.com/",
            "https://www.bilibili.com/video/BV1GJ411x7h7/",
            "https://www.4399.com/flash/34111.htm",
            "https://docs.python.org/3/library/ipaddress.html",
        ]
        for url in normal:
            with self.subTest(url=url):
                verdict = self._verdict(url)
                self.assertFalse(
                    verdict.blocked,
                    f"正常网址被拦截：{url}（原因 {verdict.reasons}）",
                )

    # -- 典型可疑 URL 应命中 ---------------------------------------------- #
    def test_public_ip_host_is_flagged(self) -> None:
        """直连公网 IP 而非域名：属于既有启发式规则。"""
        verdict = self._verdict("http://93.184.216.34/login")
        self.assertTrue(verdict.suspicious, "公网 IP 直连应被标记为可疑")
        self.assertTrue(verdict.reasons)

    def test_private_lan_ip_is_not_flagged(self) -> None:
        """局域网地址（路由器 / NAS）故意不标记，避免大量误报。"""
        for url in ("http://192.168.1.1/", "http://10.0.0.5:8080/", "http://192.0.2.10/"):
            with self.subTest(url=url):
                self.assertFalse(self._verdict(url).suspicious)

    def test_userinfo_disguise_is_flagged(self) -> None:
        verdict = self._verdict("https://example.com@evil.example.net/login")
        self.assertTrue(verdict.suspicious, "userinfo 伪装应被识别")
        self.assertTrue(verdict.reasons)

    def test_punycode_homograph_is_flagged(self) -> None:
        verdict = self._verdict("https://xn--80ak6aa92e.com/")
        self.assertTrue(verdict.suspicious, "punycode 同形异义域名应被识别")

    def test_long_url_is_flagged(self) -> None:
        verdict = self._verdict("https://example.com/" + "a" * 400)
        self.assertTrue(verdict.suspicious, "异常冗长的网址应被识别")

    def test_blacklist_domain_is_blocked(self) -> None:
        self.manager.add_blocked("phishing-example.com")
        verdict = self._verdict("https://phishing-example.com/login")
        self.assertTrue(verdict.blocked)
        self.assertEqual(verdict.level, DANGER)

    def test_whitelist_overrides_rules(self) -> None:
        self.manager.add_allowed("192.0.2.10")
        verdict = self._verdict("http://192.0.2.10/login")
        self.assertFalse(verdict.blocked, "白名单域名不应被拦截")

    def test_localhost_is_allowed_by_default(self) -> None:
        verdict = self._verdict("http://127.0.0.1:8000/")
        self.assertFalse(verdict.blocked, "本地地址不应被拦截（默认白名单）")

    # -- 语义与文案 -------------------------------------------------------- #
    def test_disclaimer_states_heuristic_nature(self) -> None:
        self.assertIn("启发式", netsec.DISCLAIMER)
        self.assertIn("不等同于", netsec.DISCLAIMER)
        self.assertIn("信誉数据库", netsec.DISCLAIMER)

    def test_titles_avoid_asserting_malice(self) -> None:
        """UI 文案不得把启发式命中直接称为"恶意"。"""
        verdict = self._verdict("http://93.184.216.34/login")
        self.assertNotIn("恶意", verdict.title)
        for level in (DANGER, WARN, OK):
            title = netsec.UrlVerdict(url="", level=level).title
            self.assertNotIn("恶意", title)

    # -- 误报 / 漏报统计（便于人工复核） ---------------------------------- #
    def test_false_positive_and_negative_summary(self) -> None:
        normal = [
            "https://github.com/", "https://www.google.com/", "https://zh.wikipedia.org/",
            "https://example.com/", "https://stackoverflow.com/questions/1",
            "https://cn.bing.com/search?q=python", "http://192.168.1.1/",
        ]
        suspicious = [
            "http://93.184.216.34/", "https://example.com@evil.example.net/",
            "https://xn--80ak6aa92e.com/", "http://paypal.com.secure-login.example.net/",
        ]
        false_positive = [u for u in normal if self._verdict(u).blocked]
        false_negative = [u for u in suspicious if not self._verdict(u).suspicious]
        print(f"\n  [统计] 正常样本 {len(normal)} 条，误报 {len(false_positive)} 条")
        print(f"  [统计] 可疑样本 {len(suspicious)} 条，漏报 {len(false_negative)} 条")
        self.assertEqual(false_positive, [], "正常站点出现误报")
        self.assertEqual(false_negative, [], "可疑站点出现漏报")


if __name__ == "__main__":
    unittest.main(verbosity=2)
