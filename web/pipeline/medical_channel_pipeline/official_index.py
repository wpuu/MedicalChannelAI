from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable


_VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
_ANNOUNCEMENT_MARKERS = ('公告', '通知', '公示', '采购', '招标', '调研')
_EMPTY_MARKERS = ('暂无公告', '暂无信息', '暂无数据', '暂无记录', '暂时没有相关信息', '没有相关信息', '未找到相关信息', '无相关记录')
_CHALLENGE_HEADINGS = ('访问验证', '安全验证', '人机验证', '验证码', '访问受限', '访问被拒绝', '登录', 'accessdenied', 'justamoment', 'verifyyouarehuman', 'checkingyourbrowser', 'verifyyourbrowser', 'captcha', 'securitycheck', 'login', 'signin')
_CHALLENGE_PROMPTS = ('请输入验证码', '请完成安全验证', '请完成人机验证', '请验证您是真人', '请先登录后访问', '请先登录', '请开启javascript', '请启用javascript', 'enablejavascriptandcookies', 'enablejavascripttocontinue')


def _compact(value: str) -> str:
    return re.sub(r'\s+', '', value).lower()


def decode_official_html(body: bytes, *, http_charset: str | None = None) -> str:
    """Honor the page's declared encoding; never hide corruption with replacement."""
    prefix = body[:8192].decode('ascii', errors='ignore')
    meta_charset = re.search(r'<meta\b[^>]*\bcharset\s*=\s*[\"\']?\s*([a-zA-Z0-9._-]+)', prefix, re.IGNORECASE)
    candidates = [http_charset, meta_charset.group(1) if meta_charset else None, 'utf-8-sig']
    for charset in dict.fromkeys(value.lower() for value in candidates if value):
        # Chinese hospital pages commonly declare GB2312 while using its GBK
        # extension. GB18030 decodes both without lossy character replacement.
        encoding = 'gb18030' if charset in {'gb2312', 'gbk', 'x-gbk'} else charset
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    raise ValueError('OFFICIAL_INDEX_ENCODING_INVALID')


class _IndexEvidence(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.visible: list[str] = []
        self.headings: list[str] = []
        self.list_text: list[str] = []
        self.password_input = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == 'input' and str(values.get('type') or '').lower() == 'password':
            self.password_input = True
        marker = _compact(str(values.get('class') or '') + ' ' + str(values.get('id') or ''))
        is_list = bool(re.search(r'(?:news|notice|article|info)[_-]?(?:list|items)|list[_-]?(?:news|notice|article|info)', marker))
        if tag not in _VOID_TAGS:
            self.stack.append((tag, is_list))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if any(tag in {'script', 'style'} for tag, _ in self.stack):
            return
        self.visible.append(data)
        if any(tag in {'title', 'h1'} for tag, _ in self.stack):
            self.headings.append(data)
        if any(is_list for _, is_list in self.stack):
            self.list_text.append(data)


def require_official_index_evidence(
    html: str,
    *,
    official_links: Iterable[tuple[str, str]],
    hospital_name: str,
    column_names: tuple[str, ...],
    error_type: type[ValueError],
    error_code: str,
) -> None:
    """Validate one bounded static index response before relevance/date filters.

    Official, dated announcement links are positive list evidence even when all
    notices are irrelevant or outside the scan window. A link-free response
    needs an explicit empty list tied to the hospital and expected column.
    This validates the fetched entry page, not pagination or 30-day coverage.
    """
    evidence = _IndexEvidence()
    evidence.feed(html)
    headings = _compact(''.join(evidence.headings))
    visible = _compact(''.join(evidence.visible))
    if (evidence.password_input
            or any(marker in headings for marker in _CHALLENGE_HEADINGS)
            or any(marker in visible for marker in _CHALLENGE_PROMPTS)):
        raise error_type(error_code)

    # Callers supply only links already checked against their official host,
    # strict dated URL identity and nonempty visible anchor text.
    if any(any(marker in title for marker in _ANNOUNCEMENT_MARKERS) for _, title in official_links):
        return

    empty_text = _compact(''.join(evidence.list_text))
    if (_compact(hospital_name) in visible
            and any(_compact(column) in visible for column in column_names)
            and any(marker in empty_text for marker in _EMPTY_MARKERS)):
        return
    raise error_type(error_code)
