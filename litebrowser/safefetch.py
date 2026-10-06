"""带 SSRF 防护的受限 HTTP 抓取。

用于 Ruffle 代理这类"由网页触发、由本程序代取外部资源"的场景。
安全策略按顺序执行，任一步不满足即拒绝：

1. **只允许 http / https**，其余 scheme（``file:`` / ``ftp:`` / ``data:`` /
   ``javascript:`` 等）一律拒绝；
2. **每次跳转都重新解析主机名**，解析出的**全部** A / AAAA 记录都必须是公网地址，
   任一为非公网即拒绝（loopback / private / link-local / multicast / reserved /
   unspecified，包含 IPv4-mapped IPv6，例如 ``::ffff:127.0.0.1``）；
3. **TCP 连接钉住在已验证的那个 IP 上**：Host 头与 TLS SNI / 证书校验仍使用域名，
   因此"校验通过后再被 DNS 重绑定"也无法把连接导向别的地址；
4. 手动处理跳转，**最多 MAX_REDIRECTS 次**，每次跳转完整重跑第 1~3 步；
5. **限制响应体积**（Content-Length 预检 + 流式读取上限双重限制）。

设计取舍：不依赖 ``urllib.request`` 的自动跳转（它会在校验之后自行连接新地址），
改用 ``http.client`` 逐跳自行控制，这样上面第 3 条才能真正成立。
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urljoin, urlsplit

#: 最多跟随的跳转次数
MAX_REDIRECTS = 5
#: 单次响应的默认体积上限
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
#: 连接与读取超时（秒）
DEFAULT_TIMEOUT = 30.0
#: 允许的 scheme
ALLOWED_SCHEMES = ("http", "https")
#: 明确视为"网页/接口响应"而非二进制资源的类型（命中即拒绝，避免拿到防盗链页面）
HTML_LIKE_TYPES = (
    "text/html",
    "text/plain",
    "application/json",
    "application/xhtml",
)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)


class FetchError(Exception):
    """抓取失败（含被安全策略拒绝）。"""


class UnsupportedScheme(FetchError):
    """scheme 不在白名单内。"""


class BlockedAddress(FetchError):
    """目标解析到了非公网地址（或被拒绝的地址形式）。"""


class TooManyRedirects(FetchError):
    """跳转次数超限。"""


class ResponseTooLarge(FetchError):
    """响应超过体积上限。"""


@dataclass
class FetchResult:
    """一次成功抓取的结果。"""

    body: bytes
    content_type: str
    final_url: str
    redirects: int


# --------------------------------------------------------------------------- #
# 地址校验
# --------------------------------------------------------------------------- #
def address_is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断单个 IP 是否属于可安全访问的公网地址。

    注意：``ipaddress`` 的 ``is_global`` 对**组播地址**（如 ``224.0.0.1``、
    ``ff02::1``）会返回 True，所以这里必须按类别逐项显式排除，
    不能只依赖 ``is_global``。同时显式处理 IPv4-mapped IPv6，
    避免 ``::ffff:127.0.0.1`` 这类地址绕过检查。
    """
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address_is_public(address.ipv4_mapped)
    if (
        address.is_unspecified
        or address.is_multicast
        or address.is_loopback
        or address.is_link_local
        or address.is_private
        or address.is_reserved
    ):
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.is_site_local:
        return False
    # 兜底：仍要求是全局可路由地址
    return bool(address.is_global)


def resolve_public(host: str, port: int | None = None) -> list[str]:
    """解析主机名并校验**全部**地址，返回可用的公网地址列表。

    只要解析结果里出现一个非公网地址就整体拒绝——这样才能挡住
    "同一域名既返回公网地址又返回 127.0.0.1" 这类重绑定攻击。
    """
    name = (host or "").strip()
    if not name:
        raise BlockedAddress("主机名为空")
    try:
        infos = socket.getaddrinfo(name, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"域名解析失败：{exc}") from exc
    if not infos:
        raise FetchError("域名没有解析结果")

    addresses: list[str] = []
    for info in infos:
        raw = str(info[4][0]).split("%", 1)[0]  # 去掉 IPv6 的 scope id
        try:
            parsed = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise BlockedAddress(f"无法解析地址：{raw}") from exc
        if not address_is_public(parsed):
            raise BlockedAddress(f"{name} 解析到非公网地址 {parsed}")
        if str(parsed) not in addresses:
            addresses.append(str(parsed))
    return addresses


def validate_url(url: str) -> tuple[str, str, int]:
    """校验 URL 的 scheme 与主机，返回 (scheme, hostname, port)。"""
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise FetchError(f"URL 无法解析：{exc}") from exc
    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsupportedScheme(f"不支持的 scheme：{scheme or '(空)'}")
    hostname = parts.hostname or ""
    if not hostname:
        raise FetchError("URL 缺少主机名")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError(f"端口非法：{exc}") from exc
    return scheme, hostname, port


# --------------------------------------------------------------------------- #
# 单跳请求（连接钉住 IP）
# --------------------------------------------------------------------------- #
def _pinned_connection(scheme: str, hostname: str, port: int, ip: str,
                       timeout: float) -> http.client.HTTPConnection:
    """建立一个 TCP 目标被钉死在 ``ip`` 上的连接。"""
    context = ssl.create_default_context() if scheme == "https" else None
    if scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            hostname, port, timeout=timeout, context=context
        )
    else:
        conn = http.client.HTTPConnection(hostname, port, timeout=timeout)

    def connect_pinned(address, _timeout, source_address=None):
        # address[1] 是端口；主机部分替换为已验证的 IP
        return socket.create_connection((ip, address[1]), _timeout, source_address)

    # http.client 在 __init__ 里把 _create_connection 设成了实例属性，
    # 因此必须在这里覆盖实例属性（类方法会被它屏蔽）
    conn._create_connection = connect_pinned  # type: ignore[method-assign]
    return conn


def _single_request(url: str, timeout: float, max_bytes: int,
                    referer: str = "") -> tuple[int, dict[str, str], bytes, str]:
    """发起一次请求（不跟随跳转），返回 (状态码, 响应头, 正文, 最终 URL)。"""
    scheme, hostname, port = validate_url(url)
    addresses = resolve_public(hostname, port)
    if not addresses:
        raise BlockedAddress("没有可用的公网地址")

    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    headers = {
        "Host": parts.netloc,
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        # 不请求压缩，避免解码引入额外复杂度与体积绕过
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    if referer and referer.lower().startswith(("http://", "https://")):
        headers["Referer"] = referer
    elif referer and referer.lower().startswith("file:"):
        # 本地内置页面发起的请求：不带 Referer，避免把本地路径发出去
        pass
    else:
        headers["Referer"] = f"{scheme}://{parts.netloc}/"

    last_error: Exception | None = None
    for ip in addresses:
        conn = _pinned_connection(scheme, hostname, port, ip, timeout)
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()

            declared = response.getheader("Content-Length")
            if declared:
                try:
                    if int(declared) > max_bytes:
                        raise ResponseTooLarge(f"声明长度 {declared} 超过上限 {max_bytes}")
                except ValueError:
                    pass

            body = bytearray()
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ResponseTooLarge(f"响应超过上限 {max_bytes} 字节")

            collected = {key.lower(): value for key, value in response.getheaders()}
            return response.status, collected, bytes(body), url
        except ResponseTooLarge:
            raise
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            last_error = exc
            continue
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - 关闭失败不影响主流程
                pass
    raise FetchError(f"连接失败：{last_error}")


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #
def fetch(
    target: str,
    *,
    referer: str = "",
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = MAX_REDIRECTS,
    validator: Callable[[bytes, str], bool] | None = None,
    reject_html_like: bool = True,
    on_hop: Callable[[str], None] | None = None,
) -> FetchResult:
    """安全地抓取一个 http/https 资源。

    :param validator: 额外内容校验，签名 ``(body, content_type) -> bool``
    :param reject_html_like: 是否拒绝 text/html 等"网页响应"类型
    :param on_hop: 每次跳转的回调（便于测试观察跳转链）
    """
    if not target:
        raise FetchError("目标为空")
    current = target
    for hop in range(max_redirects + 1):
        if on_hop is not None:
            on_hop(current)
        status, headers, body, final_url = _single_request(
            current, timeout, max_bytes, referer
        )
        if status in (301, 302, 303, 307, 308):
            location = headers.get("location") or ""
            if not location:
                raise FetchError(f"HTTP {status} 跳转缺少 Location")
            nxt = urljoin(current, location.strip())
            # 跳转目标会在下一轮循环里被完整重新校验（scheme + 全部解析地址）
            current = nxt
            continue
        if status != 200:
            raise FetchError(f"HTTP {status}")

        content_type = (headers.get("content-type") or "").split(";")[0].strip().lower()
        if reject_html_like and content_type.startswith(HTML_LIKE_TYPES):
            raise FetchError(f"返回的是网页内容（{content_type}），不是二进制资源")
        if validator is not None and not validator(body, content_type):
            raise FetchError("内容校验未通过")
        return FetchResult(body=body, content_type=content_type,
                           final_url=final_url, redirects=hop)
    raise TooManyRedirects(f"跳转超过 {max_redirects} 次")


def is_public_host(host: str) -> bool:
    """便于调用方做前置判断（失败即视为不可访问）。"""
    try:
        resolve_public(host)
    except FetchError:
        return False
    return True


def allowed_schemes() -> Iterable[str]:
    return ALLOWED_SCHEMES
