"""网络安全：HTTPS 证书校验与**可疑网址**提示。

.. important::
   本模块的网址判定是**本地启发式规则**，用于识别"看起来可疑"的 URL 特征，
   它**不是**恶意网址信誉数据库，也不是杀毒软件；命中不等于该网站一定有害，
   未命中也不代表网站安全。相关文案必须如实反映这一点（见 :data:`DISCLAIMER`）。

证书部分负责把两个内核各自返回的证书信息统一成 :class:`CertificateInfo`，
再由界面展示（颁发者、有效期、错误原因），用户可以查看详情并决定是否继续。

网址部分是一个本地判定引擎：用户黑名单 + 一组启发式规则
（IP 主机、punycode 同形异义、userinfo 伪装、敏感词、可疑端口等），
命中后由浏览器弹出提示页，而不是直接放行。
"""

from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import QObject, Signal

#: 能力边界声明：所有面向用户的提示都必须带上它，避免把启发式规则说成"恶意网址库"
DISCLAIMER = (
    "本检测基于本地启发式规则，仅用于识别可疑 URL 特征，"
    "不等同于恶意网址信誉数据库或杀毒软件。"
)

#: 命中即拦截（危险）
DANGER = "danger"
#: 命中提示但仍可继续（可疑）
WARN = "warn"
#: 正常
OK = "ok"

#: 常见钓鱼关键词
SENSITIVE_WORDS = (
    "login", "signin", "sign-in", "verify", "verification", "account", "password",
    "passwd", "secure", "security", "update", "confirm", "bank", "pay", "paypal",
    "wallet", "recharge", "gift", "free", "bonus", "lottery", "invoice",
    "登录", "验证", "账户", "账号", "密码", "安全", "更新", "中奖", "红包", "支付",
)

#: 与敏感词组合时报警的高风险免费后缀
RISKY_TLDS = (
    ".tk", ".top", ".xyz", ".gq", ".cf", ".ml", ".ga", ".work", ".click",
    ".link", ".loan", ".download", ".racing", ".review", ".stream",
)

#: 常见可信后缀（出现在黑名单以外时降低误报）
SAFE_SCHEMES = ("https", "file", "about", "data", "view-source", "lite")


@dataclass
class CertificateInfo:
    """统一的证书信息。"""

    host: str = ""
    subject: str = ""
    issuer: str = ""
    valid_from: str = ""
    valid_to: str = ""
    error: str = ""
    is_error: bool = False
    severity: str = OK            # ok | warn | danger
    raw: object = None

    @property
    def summary(self) -> str:
        if self.is_error:
            return f"证书不受信任：{self.error}"
        return f"证书有效（颁发者：{self.issuer or '未知'}）"


@dataclass
class UrlVerdict:
    """一次网址检查的结论。"""

    level: str = OK
    reasons: list[str] = field(default_factory=list)
    url: str = ""

    @property
    def blocked(self) -> bool:
        return self.level == DANGER

    @property
    def suspicious(self) -> bool:
        return self.level in (DANGER, WARN)

    @property
    def title(self) -> str:
        return {
            DANGER: "已拦截：该网址命中本地可疑规则",
            WARN: "该网址看起来可疑",
        }.get(self.level, "网址状态")


class SecurityManager(QObject):
    """网址判定 + 证书信息整理。"""

    changed = Signal()

    def __init__(self, config, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.data_dir = Path(data_dir)
        self.list_path = self.data_dir / "blocklist.txt"
        self._blocked: set[str] = set()
        self._allowed: set[str] = set()
        self.load()

    # ------------------------------------------------------------------ #
    # 名单
    # ------------------------------------------------------------------ #
    def load(self) -> None:
        self._blocked = set()
        self._allowed = set()
        if not self.list_path.exists():
            self._write_default_list()
        try:
            for line in self.list_path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("!"):
                    self._allowed.add(self._normalize(line[1:]))
                else:
                    self._blocked.add(self._normalize(line))
        except OSError:
            pass

    def _write_default_list(self) -> None:
        content = """# lite browser 网址黑名单
# 每行一个域名（可写 example.com 或 *.example.com），注释以 # 开头
# 以 ! 开头表示白名单（即使命中规则也放行），例如：!mybank.com
#
# 以下域名仅作示例，默认不拦截（已注释）
# phishing-example.com
# *.malware-example.net
!localhost
!127.0.0.1
"""
        try:
            self.list_path.parent.mkdir(parents=True, exist_ok=True)
            self.list_path.write_text(content, encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _normalize(value: str) -> str:
        value = value.strip().lower()
        value = re.sub(r"^[a-z]+://", "", value)
        value = value.split("/")[0]
        value = value.split(":")[0]
        return value.lstrip("*.")

    def blocked_domains(self) -> list[str]:
        return sorted(self._blocked)

    def allowed_domains(self) -> list[str]:
        return sorted(self._allowed)

    def add_blocked(self, domain: str) -> None:
        domain = self._normalize(domain)
        if domain:
            self._blocked.add(domain)
            self.save()
            self.changed.emit()

    def remove_blocked(self, domain: str) -> None:
        self._blocked.discard(self._normalize(domain))
        self.save()
        self.changed.emit()

    def add_allowed(self, domain: str) -> None:
        domain = self._normalize(domain)
        if domain:
            self._allowed.add(domain)
            self.save()
            self.changed.emit()

    def remove_allowed(self, domain: str) -> None:
        self._allowed.discard(self._normalize(domain))
        self.save()
        self.changed.emit()

    def save(self) -> None:
        lines = [
            "# lite browser 网址黑名单（每行一个域名，# 注释，! 表示白名单）",
        ]
        lines += sorted(self._blocked)
        lines += ["!" + item for item in sorted(self._allowed)]
        try:
            self.list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # 判定
    # ------------------------------------------------------------------ #
    @staticmethod
    def domain_of(url: str) -> str:
        try:
            host = urlsplit(url).hostname or ""
        except ValueError:
            return ""
        return host.lower()

    def is_allowed(self, host: str) -> bool:
        host = (host or "").lower()
        for item in self._allowed:
            if host == item or host.endswith("." + item):
                return True
        return False

    def _in_blocklist(self, host: str) -> bool:
        host = (host or "").lower()
        for item in self._blocked:
            if host == item or host.endswith("." + item):
                return True
        return False

    def check_url(self, url: str, *, enabled: Optional[bool] = None) -> UrlVerdict:
        """检查网址是否可疑。"""
        verdict = UrlVerdict(url=url)
        if enabled is None:
            enabled = bool(self.config.get("block_malicious"))
        if not enabled or not url:
            return verdict

        lowered = url.strip().lower()
        if lowered.startswith(("about:", "data:", "file:", "lite:", "view-source:")):
            return verdict
        try:
            parts = urlsplit(url)
        except ValueError:
            return verdict

        host = (parts.hostname or "").lower()
        if not host:
            return verdict

        if self.is_allowed(host):
            return verdict

        if self._in_blocklist(host):
            verdict.level = DANGER
            verdict.reasons.append("该域名在您的黑名单中")
            return verdict

        reasons: list[str] = []
        level = OK

        def raise_level(new: str) -> None:
            nonlocal level
            order = {OK: 0, WARN: 1, DANGER: 2}
            if order[new] > order[level]:
                level = new

        # 1) userinfo 伪装：http://trusted.com@evil.com
        if "@" in (parts.netloc or ""):
            raise_level(DANGER)
            reasons.append("网址中使用了 @ 伪装真实域名（常见钓鱼手法）")

        # 2) IP 直连 + 非标准端口
        try:
            ip = ipaddress.ip_address(host)
            is_ip = True
            if not ip.is_private:
                raise_level(WARN)
                reasons.append("直接使用 IP 地址访问，而非域名")
        except ValueError:
            is_ip = False

        port = parts.port
        if port and port not in (80, 443, 8080, 8443) and is_ip:
            raise_level(DANGER)
            reasons.append(f"使用了非常规端口 {port}")

        # 3) punycode 同形异义
        if "xn--" in host:
            raise_level(DANGER)
            reasons.append("域名包含 punycode（可能是同形异义钓鱼域名）")

        # 4) 敏感词 + 非 https
        decoded = unquote(lowered)
        hits = [word for word in SENSITIVE_WORDS if word in decoded]
        if hits:
            if parts.scheme == "http":
                raise_level(DANGER)
                reasons.append(
                    "网址包含敏感词（" + "、".join(hits[:3]) + "）且未使用 HTTPS 加密"
                )
            else:
                raise_level(WARN)
                reasons.append("网址包含敏感词：" + "、".join(hits[:3]))

        # 5) 高风险后缀 + 敏感词
        if any(host.endswith(tld) for tld in RISKY_TLDS):
            if hits:
                raise_level(DANGER)
                reasons.append("高风险域名后缀与敏感词同时出现")
            else:
                raise_level(WARN)
                reasons.append("该域名使用了较高风险的后缀")

        # 6) 子域名过多
        labels = host.split(".")
        if len(labels) >= 5:
            raise_level(WARN)
            reasons.append(f"子域名层级过多（{len(labels)} 级），可能是随机生成的域名")

        # 7) 连字符过多
        if len(labels) >= 2:
            main = labels[-2]
            if main.count("-") >= 3:
                raise_level(WARN)
                reasons.append("主域名中包含大量连字符")

        # 8) 超长网址
        if len(url) > 320:
            raise_level(WARN)
            reasons.append("网址异常冗长，可能隐藏真实跳转地址")

        # 9) 十六进制 / 百分号编码的域名（把恶意域名藏起来）
        if re.search(r"%[0-9a-f]{2}", parts.netloc or "", re.I):
            raise_level(WARN)
            reasons.append("域名中包含大量转义字符")

        verdict.level = level
        verdict.reasons = reasons
        return verdict

    # ------------------------------------------------------------------ #
    # 证书
    # ------------------------------------------------------------------ #
    def check_certificate(self, info: CertificateInfo) -> CertificateInfo:
        """根据证书信息判定严重程度。"""
        if not info.is_error:
            info.severity = OK
            return info
        text = (info.error or "").lower()
        if any(word in text for word in ("过期", "expired", "not yet", "尚未", "无效")):
            info.severity = DANGER
        elif any(word in text for word in ("证书名称", "名称不匹配", "mismatch", "主机名")):
            info.severity = DANGER
        elif any(word in text for word in ("自签名", "self-signed", "不受信任", "untrusted", "unknown authority")):
            info.severity = DANGER
        else:
            info.severity = WARN
        return info

    @staticmethod
    def describe_time(value) -> str:
        """把各种时间表示为可读文本。"""
        if not value:
            return ""
        if isinstance(value, (int, float)):
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))
        text = str(value)
        return text[:16].replace("T", " ") if "T" in text else text[:24]

    def allowed_hosts_text(self) -> str:
        return "\n".join(self.allowed_domains()) or "（无）"

    def blocked_hosts_text(self) -> str:
        return "\n".join(self.blocked_domains()) or "（无）"


def security_icon(level: str) -> str:
    """返回状态对应的图标名。"""
    return {"ok": "lock", "warn": "warn", "danger": "warn"}.get(level, "lock")


def hosts_from_text(text: str) -> Iterable[str]:
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            yield line
