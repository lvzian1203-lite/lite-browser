"""界面多语言（中文（简体）/ English）。

设计取舍：

* **以中文原文作为键**。项目已有 900 多处中文界面文字，若改用 ``ui.ok`` 之类的
  抽象键，需要同时改动所有调用点且失去可读性；直接以原文为键，包装处
  ``tr("后退")`` 一眼就能看懂，漏翻时也只会退回中文而不是显示键名。
* ``tr()`` 在中文环境下**原样返回**，不产生任何额外开销（只做一次字典判定）。
* 带插值的文本用 :func:`trf`：``trf("共 {0} 个", count)``。
  模板里的 ``{0}`` 是占位符，翻译时保持同样的占位符即可。
* 语言由 ``settings.json`` 的 ``ui_language`` 保存（``zh_CN`` / ``en``）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

LANGUAGE_ZH = "zh_CN"
LANGUAGE_EN = "en"
DEFAULT_LANGUAGE = LANGUAGE_ZH

#: 可切换的语言（顺序即设置页下拉框顺序）
LANGUAGES: list[tuple[str, str]] = [
    (LANGUAGE_ZH, "中文（简体）"),
    (LANGUAGE_EN, "English"),
]

_current = DEFAULT_LANGUAGE
_catalog: dict[str, str] = {}


def available_languages() -> list[tuple[str, str]]:
    return list(LANGUAGES)


def language_name(code: str) -> str:
    for item, name in LANGUAGES:
        if item == code:
            return name
    return name_of_default()


def name_of_default() -> str:
    return LANGUAGES[0][1]


def normalize_language(code: str | None) -> str:
    """把任意输入归一成受支持的语言代码。"""
    text = str(code or "").strip().replace("-", "_").lower()
    if not text:
        return DEFAULT_LANGUAGE
    if text in ("en", "en_us", "english", "eng"):
        return LANGUAGE_EN
    if text in ("zh", "zh_cn", "zh_hans", "cn", "chinese", "中文", "简体中文"):
        return LANGUAGE_ZH
    for item, _ in LANGUAGES:
        if item.lower() == text:
            return item
    return DEFAULT_LANGUAGE


def set_language(code: str | None) -> str:
    """设置当前语言并返回归一化后的代码。"""
    global _current
    _current = normalize_language(code)
    return _current


def current_language() -> str:
    return _current


def is_english() -> bool:
    return _current == LANGUAGE_EN


def tr(text: str) -> str:
    """翻译一条界面文字；没有译文时返回原文（中文）。

    查找时对首尾空白容错：f-string 自动包装出来的模板常常带着换行/缩进
    （例如 ``"\\n报告已保存：{0}\\n"``），而译文表里的键是去掉空白的版本。
    命中后在译文两侧补回原有空白，保证拼出来的文本排版不变。
    """
    if _current == LANGUAGE_ZH or not text:
        return text
    translated = _catalog.get(text)
    if translated:
        return translated
    stripped = text.strip()
    if stripped and stripped != text:
        hit = _catalog.get(stripped)
        if hit:
            head = text[: len(text) - len(text.lstrip())]
            tail = text[len(text.rstrip()):]
            return head + hit + tail
    return text


def trf(template: str, *args: Any) -> str:
    """翻译带插值的模板并格式化。

    ``trf("共 {0} 个文件", count)`` —— 模板里的 ``{0}`` 在译文里保持不变。
    """
    pattern = tr(template) if _current != LANGUAGE_ZH else template
    if not args:
        return pattern
    try:
        return pattern.format(*args)
    except (IndexError, KeyError, ValueError) as exc:
        # 译文占位符写错时不能让界面崩掉：退回中文模板
        log.warning("多语言模板格式错误：%r（%s）", pattern, exc)
        try:
            return template.format(*args)
        except (IndexError, KeyError, ValueError):
            return template


def tr_text(text: str) -> str:
    """长文本（错误页 HTML、帮助正文、诊断报告）的短语级翻译。

    这类内容动辄几百字，整体塞进翻译表既臃肿又难维护。
    这里按"整段 → 逐行 → 逐句"三级查找：命中就替换，没命中就保留中文，
    因此可以增量翻译——今天翻几行，明天再补几行，界面永远不会崩。

    中文环境下**原样返回**，没有任何额外开销。
    """
    if _current == LANGUAGE_ZH or not text:
        return text
    direct = _catalog.get(text)
    if direct:
        return direct

    def translate_line(line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return line
        hit = _catalog.get(stripped)
        if hit:
            # 保留原有缩进
            indent = line[: len(line) - len(line.lstrip())]
            return indent + hit
        return line

    return "\n".join(translate_line(line) for line in text.splitlines())


def tr_html(html: str) -> str:
    """对内置页面的 HTML 做短语级翻译。

    错误页 / 提示页 / 自检页是一整段几百字的 HTML 模板，整体翻译既臃肿又容易
    漏掉标签。这里按"已知短语最长优先"做替换：命中的中文片段换成英文，
    标签与样式原样保留，没命中的部分保持中文。

    中文环境或没有命中时**原样返回**。
    """
    if _current == LANGUAGE_ZH or not html:
        return html
    result = html
    # 长短语优先，避免"后退"先把"后退到安全页面"里的部分替换掉
    for phrase in sorted(_catalog, key=len, reverse=True):
        if len(phrase) < 2 or "{" in phrase or "<" in phrase:
            continue
        if phrase in result:
            result = result.replace(phrase, _catalog[phrase])
    return result


def load_catalog(catalog: dict[str, str]) -> int:
    """载入翻译表（供测试或按需替换）。返回条目数。"""
    _catalog.clear()
    _catalog.update({key: value for key, value in catalog.items() if value})
    return len(_catalog)


def catalog() -> dict[str, str]:
    return dict(_catalog)


def missing_translations(strings) -> list[str]:
    """列出给定字符串里缺少译文的条目（供覆盖率测试使用）。"""
    return [item for item in strings if item and item not in _catalog]


def apply_language_from_config(config) -> str:
    """按配置里的 ``ui_language`` 设定语言（程序启动时调用）。"""
    try:
        code = config.get("ui_language") if config is not None else None
    except Exception:  # noqa: BLE001 - 配置不可用时退回默认语言
        code = None
    return set_language(code or os.environ.get("LITE_BROWSER_LANG"))


def _install_default_catalog() -> None:
    """载入内置翻译表（自动生成的 catalog_en + 手工维护的 catalog_extra）。"""
    try:
        from .catalog_en import CATALOG as EN_CATALOG

        load_catalog(EN_CATALOG)
    except ImportError:  # 尚未生成翻译表时也能正常运行
        log.debug("未找到内置英文翻译表，界面保持中文")
    try:
        from .catalog_extra import EXTRA

        load_catalog({**_catalog, **EXTRA})  # 手工条目优先，便于临时修正
    except ImportError:
        log.debug("未找到手工翻译表 catalog_extra")


_install_default_catalog()
