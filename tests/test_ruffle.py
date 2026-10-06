"""Ruffle 代理与会话授权的单元测试（P0-1 / P0-2）。"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from litebrowser import ruffle, safefetch  # noqa: E402

SWF = b"FWS" + b"\x0a\x00\x00\x00" + b"\x00" * 32
NOT_SWF = b"<html><body>not a flash file</body></html>"


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/good.swf":
            self._send(200, "application/x-shockwave-flash", SWF)
        elif path == "/fake.swf":
            # 防盗链站点常见的返回：文件名是 .swf，内容是 HTML
            self._send(200, "text/html; charset=utf-8", NOT_SWF)
        else:
            self._send(404, "text/plain", b"nope")

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


class RuffleSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sessions = ruffle.RuffleSessions()

    def test_token_is_random_and_long(self) -> None:
        tokens = {self.sessions.create() for _ in range(50)}
        self.assertEqual(len(tokens), 50, "token 不应重复")
        for token in tokens:
            self.assertGreaterEqual(len(token), 32)
            self.assertTrue(self.sessions.valid(token))

    def test_forged_token_is_rejected(self) -> None:
        self.sessions.create()
        self.assertFalse(self.sessions.valid(""))
        self.assertFalse(self.sessions.valid("not-a-real-token"))
        self.assertFalse(self.sessions.valid("a" * 43))

    def test_revoke_invalidates_token(self) -> None:
        token = self.sessions.create()
        self.assertTrue(self.sessions.valid(token))
        self.sessions.revoke(token)
        self.assertFalse(self.sessions.valid(token))

    def test_revoke_all(self) -> None:
        tokens = [self.sessions.create() for _ in range(5)]
        self.sessions.revoke_all()
        for token in tokens:
            self.assertFalse(self.sessions.valid(token))

    def test_expired_token_is_invalid(self) -> None:
        token = self.sessions.create()
        with self.sessions._lock:  # noqa: SLF001 - 测试需要直接改过期时间
            self.sessions._tokens[token] = time.time() - 1
        self.assertFalse(self.sessions.valid(token))

    def test_session_limit_evicts_oldest(self) -> None:
        tokens = [self.sessions.create() for _ in range(self.sessions.MAX_SESSIONS + 5)]
        self.assertLessEqual(self.sessions.count(), self.sessions.MAX_SESSIONS)
        self.assertFalse(self.sessions.valid(tokens[0]), "最早的 token 应被淘汰")

    def test_proxy_url_round_trip_with_token(self) -> None:
        token = self.sessions.create()
        target = "https://example.com/a.swf?x=1"
        url = ruffle.proxy_url(target, token)
        self.assertIn("token=", url)
        parsed_target, parsed_token = ruffle.parse_proxy_request(url)
        self.assertEqual(parsed_target, target)
        self.assertEqual(parsed_token, token)
        self.assertEqual(ruffle.unproxy_target(url), target)

    def test_bootstrap_script_embeds_token(self) -> None:
        token = self.sessions.create()
        script = ruffle.bootstrap_script(token=token)
        self.assertIn(token, script)
        self.assertIn("proxy?token=", script)

    def test_swf_page_uses_token(self) -> None:
        token = self.sessions.create()
        page = ruffle.swf_page("https://example.com/a.swf", token)
        self.assertIn(token, page)
        self.assertIn("/proxy?token=", page)


class _QuietServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:  # noqa: D102
        return


class SwfFetchTests(unittest.TestCase):
    """fetch_swf 的安全边界：只接受 http/https 的真实 SWF。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _QuietServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls._real_resolve = safefetch.resolve_public

    @classmethod
    def tearDownClass(cls) -> None:
        safefetch.resolve_public = cls._real_resolve
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        safefetch.resolve_public = self._real_resolve

    def _allow_loopback(self) -> None:
        safefetch.resolve_public = lambda host, port=None: ["127.0.0.1"]

    def test_non_swf_url_is_rejected(self) -> None:
        self.assertIsNone(ruffle.fetch_swf("https://example.com/page.html"))
        self.assertIsNone(ruffle.fetch_swf("file:///c:/x.swf"))
        self.assertIsNone(ruffle.fetch_swf(""))

    def test_localhost_is_rejected_by_real_policy(self) -> None:
        """真实策略下（不放宽）本机地址必须被拒绝。"""
        self.assertIsNone(ruffle.fetch_swf(f"{self.base}/good.swf"))

    def test_valid_swf_is_returned(self) -> None:
        self._allow_loopback()
        result = ruffle.fetch_swf(f"{self.base}/good.swf")
        self.assertIsNotNone(result)
        body, mime = result
        self.assertEqual(body, SWF)
        self.assertIn("shockwave", mime)

    def test_html_masquerading_as_swf_is_rejected(self) -> None:
        self._allow_loopback()
        self.assertIsNone(ruffle.fetch_swf(f"{self.base}/fake.swf"))

    def test_is_swf_url(self) -> None:
        self.assertTrue(ruffle.is_swf_url("http://a.com/game.swf"))
        self.assertTrue(ruffle.is_swf_url("http://a.com/game.SWF?v=1"))
        self.assertFalse(ruffle.is_swf_url("http://a.com/game.swf.html"))
        self.assertFalse(ruffle.is_swf_url("http://a.com/"))

    def test_supports_current_engine(self) -> None:
        self.assertTrue(ruffle.supports_current_engine("webview2"))
        self.assertFalse(ruffle.supports_current_engine("qtwebengine"))

    def test_serve_only_allows_whitelisted_names(self) -> None:
        self.assertIsNotNone(ruffle.serve("ruffle.js"), "随包分发的 ruffle.js 应可读取")
        self.assertIsNone(ruffle.serve("../litebrowser/config.py"))
        self.assertIsNone(ruffle.serve("x.exe"))
        self.assertIsNone(ruffle.serve(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
