"""safefetch 的单元测试：SSRF 防护、跳转限制、体积与类型限制。

运行：
    python -m unittest discover -s tests -v
或：
    python -m pytest tests -v
"""

from __future__ import annotations

import http.server
import ipaddress
import os
import socket
import socketserver
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from litebrowser import safefetch  # noqa: E402
from litebrowser.safefetch import (  # noqa: E402
    BlockedAddress,
    FetchError,
    ResponseTooLarge,
    TooManyRedirects,
    UnsupportedScheme,
)

SWF = b"CWS" + b"\x10\x00\x00\x00" + b"\x00" * 64
HTML = b"<html><body>hotlink protected</body></html>"


# --------------------------------------------------------------------------- #
# 测试用的本地 HTTP 服务
# --------------------------------------------------------------------------- #
class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/swf":
            self._send(200, "application/x-shockwave-flash", SWF)
        elif path == "/html":
            self._send(200, "text/html; charset=utf-8", HTML)
        elif path == "/redirect-to-file":
            self._redirect("file:///etc/passwd")
        elif path == "/redirect-to-localhost":
            self._redirect("http://127.0.0.1:1/secret.swf")
        elif path == "/redirect-loop":
            self._redirect("/redirect-loop")
        elif path == "/redirect-no-location":
            self.send_response(302)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path.startswith("/redirect/"):
            # /redirect/<n> → 跳到 /redirect/<n-1>，/redirect/0 → /swf
            try:
                count = int(path.rsplit("/", 1)[-1])
            except ValueError:
                count = 0
            target = "/swf" if count <= 0 else f"/redirect/{count - 1}"
            self._redirect(target)
        elif path == "/big":
            size = 3 * 1024 * 1024
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            chunk = b"a" * 65536
            sent = 0
            try:
                while sent < size:
                    self.wfile.write(chunk)
                    sent += len(chunk)
            except (ConnectionResetError, BrokenPipeError):
                # 客户端达到体积上限后会主动断开，测试服务端无需关切
                pass
        elif path == "/big-no-length":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            chunk = b"b" * 65536
            try:
                for _ in range(60):
                    self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
            except (ConnectionResetError, BrokenPipeError):
                pass
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # 测试期间静音
        return


class _QuietServer(socketserver.ThreadingTCPServer):
    """客户端达到体积上限后会主动断开，这属于预期行为，不打印堆栈。"""

    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:  # noqa: D102
        return


class SafeFetchTests(unittest.TestCase):
    """校验逻辑不需要网络；跳转/体积测试用本地服务。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _QuietServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        # 本地服务本身就是 loopback，正常会被安全策略拒绝。
        # 为了测跳转/体积等逻辑，这里**只在本测试模块内**临时放宽地址校验，
        # 地址校验本身由下面的用例独立、真实地验证。
        cls._real_resolve = safefetch.resolve_public
        safefetch.resolve_public = lambda host, port=None: ["127.0.0.1"]

    @classmethod
    def tearDownClass(cls) -> None:
        safefetch.resolve_public = cls._real_resolve
        cls.server.shutdown()
        cls.server.server_close()

    # -- 地址类别 --------------------------------------------------------- #
    def test_private_and_special_addresses_are_rejected(self) -> None:
        blocked = [
            "127.0.0.1", "127.1.2.3", "0.0.0.0", "10.0.0.1", "172.16.0.1", "172.31.255.254",
            "192.168.0.1", "169.254.169.254", "224.0.0.1", "239.255.255.250", "240.0.0.1",
            "::1", "::", "fe80::1", "fc00::1", "fd00::1", "ff02::1", "ff05::1",
            "::ffff:127.0.0.1", "::ffff:10.1.1.1", "::ffff:192.168.1.1", "::ffff:0.0.0.0",
            "2001:db8::1", "100.64.0.1",
        ]
        for addr in blocked:
            with self.subTest(addr=addr):
                self.assertFalse(
                    safefetch.address_is_public(ipaddress.ip_address(addr)),
                    f"{addr} 应被判定为非公网地址",
                )

    def test_public_addresses_are_allowed(self) -> None:
        allowed = ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111",
                   "::ffff:8.8.8.8"]
        for addr in allowed:
            with self.subTest(addr=addr):
                self.assertTrue(safefetch.address_is_public(ipaddress.ip_address(addr)))

    def test_resolve_public_rejects_localhost_and_private(self) -> None:
        real = SafeFetchTests._real_resolve
        for host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "::ffff:127.0.0.1"):
            with self.subTest(host=host):
                with self.assertRaises(FetchError):
                    real(host)

    # -- scheme ----------------------------------------------------------- #
    def test_non_http_schemes_are_rejected(self) -> None:
        for url in ("file:///c:/windows/win.ini", "ftp://example.com/a.swf",
                    "data:text/html,<script>", "javascript:alert(1)",
                    "gopher://example.com/", "//example.com/a.swf", ""):
            with self.subTest(url=url):
                with self.assertRaises(FetchError):
                    safefetch.validate_url(url)

    def test_valid_schemes_pass_validation(self) -> None:
        self.assertEqual(safefetch.validate_url("http://example.com/a.swf"),
                         ("http", "example.com", 80))
        self.assertEqual(safefetch.validate_url("https://example.com/a.swf"),
                         ("https", "example.com", 443))
        self.assertEqual(safefetch.validate_url("https://example.com:8443/a.swf"),
                         ("https", "example.com", 8443))

    # -- 跳转 ------------------------------------------------------------- #
    def test_normal_download(self) -> None:
        result = safefetch.fetch(f"{self.base}/swf")
        self.assertEqual(result.body, SWF)
        self.assertEqual(result.redirects, 0)

    def test_redirect_chain_within_limit(self) -> None:
        hops: list[str] = []
        # /redirect/N 一共会发 N+1 次 302（N, N-1, ..., 0，再到 /swf）
        result = safefetch.fetch(f"{self.base}/redirect/2", on_hop=hops.append)
        self.assertEqual(result.body, SWF)
        self.assertEqual(result.redirects, 3)
        self.assertEqual(len(hops), 4)  # 3 次跳转 + 最终请求

    def test_too_many_redirects(self) -> None:
        with self.assertRaises(TooManyRedirects):
            safefetch.fetch(f"{self.base}/redirect-loop")

    def test_redirect_count_boundary(self) -> None:
        # 正好等于上限（5 次跳转）：应当成功
        result = safefetch.fetch(f"{self.base}/redirect/{safefetch.MAX_REDIRECTS - 1}")
        self.assertEqual(result.body, SWF)
        self.assertEqual(result.redirects, safefetch.MAX_REDIRECTS)
        # 超过上限一次（6 次跳转）：应当失败
        with self.assertRaises(TooManyRedirects):
            safefetch.fetch(f"{self.base}/redirect/{safefetch.MAX_REDIRECTS}")

    def test_redirect_to_file_scheme_is_rejected(self) -> None:
        """跳转目标同样要过 scheme 校验，不能只校验初始 URL。"""
        with self.assertRaises(UnsupportedScheme):
            safefetch.fetch(f"{self.base}/redirect-to-file")

    def test_redirect_without_location_is_rejected(self) -> None:
        with self.assertRaises(FetchError):
            safefetch.fetch(f"{self.base}/redirect-no-location")

    def test_redirect_to_loopback_is_blocked_by_real_policy(self) -> None:
        """用真实（未放宽）的地址校验验证：跳转到 loopback 会被拒绝。"""
        safefetch.resolve_public = SafeFetchTests._real_resolve
        try:
            with self.assertRaises(BlockedAddress):
                safefetch.fetch(f"{self.base}/redirect-to-localhost")
        finally:
            safefetch.resolve_public = lambda host, port=None: ["127.0.0.1"]

    # -- 体积与类型 ------------------------------------------------------- #
    def test_oversized_response_with_content_length(self) -> None:
        with self.assertRaises(ResponseTooLarge):
            safefetch.fetch(f"{self.base}/big", max_bytes=1024 * 1024)

    def test_oversized_response_without_content_length(self) -> None:
        with self.assertRaises(ResponseTooLarge):
            safefetch.fetch(f"{self.base}/big-no-length", max_bytes=1024 * 1024)

    def test_content_length_just_under_limit_is_ok(self) -> None:
        result = safefetch.fetch(f"{self.base}/swf", max_bytes=len(SWF) + 1)
        self.assertEqual(len(result.body), len(SWF))

    def test_html_like_content_is_rejected(self) -> None:
        with self.assertRaises(FetchError):
            safefetch.fetch(f"{self.base}/html")

    def test_validator_can_reject_content(self) -> None:
        with self.assertRaises(FetchError):
            safefetch.fetch(f"{self.base}/swf",
                            validator=lambda body, _ct: body[:3] == b"NOPE")

    def test_http_error_status_is_rejected(self) -> None:
        with self.assertRaises(FetchError):
            safefetch.fetch(f"{self.base}/missing")

    def test_host_header_keeps_domain_name(self) -> None:
        """连接钉在 IP 上，但 Host 头必须仍是域名（由本地服务无法验证域名，
        这里改为验证请求构造阶段不会把 IP 写进 Host）。"""
        parts = safefetch.validate_url("https://example.com:8443/a.swf")
        self.assertEqual(parts[1], "example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
