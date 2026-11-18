"""维基 API 封装（SPEC §5.7）：摘要 / 跨语言链接 / 外链 / redirects 别名。

所有函数失败时返回空值不抛异常；带 User-Agent 与限速。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

UA = "OpenMind/0.1 (daily knowledge digest; +https://github.com/lightai1235/news)"
RATE_SLEEP = 0.5


@dataclass
class ArticleInfo:
    title: str
    lang: str
    extract: str = ""
    zh_title: str = ""
    aliases: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)


def _api(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def _get(params: dict, lang: str) -> dict:
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        resp = client.get(
            _api(lang), params={**params, "format": "json", "formatversion": 2}, timeout=15.0
        )
        resp.raise_for_status()
        time.sleep(RATE_SLEEP)
        return resp.json()


def _first_page(data: dict) -> dict:
    pages = data.get("query", {}).get("pages", [])
    if isinstance(pages, dict):
        pages = list(pages.values())
    return pages[0] if pages else {}


def fetch_article(title: str, lang: str = "en") -> ArticleInfo:
    info = ArticleInfo(title=title, lang=lang)
    try:
        data = _get(
            {
                "action": "query",
                "titles": title,
                "prop": "extracts|langlinks|categories",
                "exintro": 1,
                "explaintext": 1,
                "lllang": "zh",
                "lllimit": 5,
                "cllimit": 50,
                "clshow": "!hidden",
                "redirects": 1,
            },
            lang,
        )
        page = _first_page(data)
        info.extract = page.get("extract", "")
        for ll in page.get("langlinks", []):
            if ll.get("lang") == "zh":
                info.zh_title = ll.get("title", "")
        for cat in page.get("categories", []):
            t = cat.get("title", "") if isinstance(cat, dict) else str(cat)
            # 去掉 "Category:" / "分类:" 前缀
            t = re.sub(r"^(Category|分類|分类):", "", t)
            if t:
                info.categories.append(t)
    except Exception as exc:
        log.warning("wiki fetch_article %s failed: %s", title, exc)
    return info


def fetch_fulltext(title: str, lang: str = "en") -> str:
    """整篇正文纯文本（无 exintro），供最终 3 条的全文合规复核。失败返回空串。"""
    try:
        data = _get(
            {
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "explaintext": 1,
                "redirects": 1,
            },
            lang,
        )
        return _first_page(data).get("extract", "")
    except Exception as exc:
        log.warning("wiki fetch_fulltext %s failed: %s", title, exc)
        return ""


def fetch_external_links(title: str, lang: str = "en") -> list[str]:
    try:
        data = _get(
            {
                "action": "query",
                "titles": title,
                "prop": "externallinks",
                "ellimit": 100,
                "redirects": 1,
            },
            lang,
        )
        page = _first_page(data)
        links = [e["url"] if isinstance(e, dict) else e for e in page.get("externallinks", [])]
        if not links:
            # 可观测性：200 但空时记录页面形态，区分「真无外链」与「响应异常」
            log.info(
                "wiki externallinks empty for %s (lang=%s): page_keys=%s missing=%s",
                title,
                lang,
                sorted(page.keys()),
                page.get("missing", False),
            )
        return links
    except Exception as exc:
        log.warning("wiki fetch_external_links %s failed: %s", title, exc)
        return []


_EXT_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+")
# 只匹配 <ref ...>...</ref> 引用块；自闭合 <ref name=x />（复用引用）不含新 URL，天然跳过
_REF_BLOCK_RE = re.compile(r"<ref\b[^>]*>(.*?)</ref>", re.DOTALL | re.IGNORECASE)
# Wayback 存档前缀：https://web.archive.org/web/<时间戳>[修饰符]/<原始URL>
_WAYBACK_RE = re.compile(
    r"^https?://web\.archive\.org/web/\d+[a-z_]*/(https?://.+)$", re.IGNORECASE
)
# 维基家族与基建噪声域名：自链、坐标工具、XML 命名空间等，非内容信源
_NOISE_HOSTS = (
    "wikipedia.org",
    "wikimedia.org",
    "wikidata.org",
    "wikiquote.org",
    "wiktionary.org",
    "wikisource.org",
    "wikinews.org",
    "wikibooks.org",
    "wikiversity.org",
    "wikivoyage.org",
    "toolforge.org",
    "wmflabs.org",
    "w3.org",
)


def _is_noise_host(host: str) -> bool:
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in _NOISE_HOSTS)


def unwrap_archive(url: str) -> str:
    """Wayback 存档链接还原为原始 URL；非存档链接原样返回。"""
    m = _WAYBACK_RE.match(url)
    return m.group(1) if m else url


def fetch_reference_links(title: str, lang: str = "en") -> list[str]:
    """参考文献外链兜底：只解析渲染 HTML 的 <ref> 引用块（A 方案）。

    externallinks 只含「外部链接」章节；大量词条的权威来源在参考文献里。
    整页正则扫描会混入信息框坐标、命名空间、导航等噪声（2026-11-18 修正），
    因此只取 <ref> 块内 URL；Wayback 存档归一为原始 URL 去重（C 方案）。
    """
    try:
        data = _get({"action": "parse", "page": title, "prop": "text", "redirects": 1}, lang)
        html = data.get("parse", {}).get("text", "")
        if isinstance(html, dict):  # fv2 某些版本 text 为 {"*": ...}
            html = html.get("*", "")
        urls: list[str] = []
        seen: set[str] = set()
        for block in _REF_BLOCK_RE.finditer(html):
            for m in _EXT_URL_RE.finditer(block.group(1)):
                url = unwrap_archive(m.group(0).rstrip(".,;)"))
                host = urlparse(url).hostname or ""
                if _is_noise_host(host):
                    continue
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls[:100]
    except Exception as exc:
        log.warning("wiki fetch_reference_links %s failed: %s", title, exc)
        return []


def fetch_aliases(title: str, lang: str = "en") -> list[str]:
    try:
        data = _get(
            {
                "action": "query",
                "list": "backlinks",
                "bltitle": title,
                "blfilterredir": "redirects",
                "bllimit": 20,
            },
            lang,
        )
        return [r["title"] for r in data.get("query", {}).get("backlinks", [])]
    except Exception as exc:
        log.warning("wiki fetch_aliases %s failed: %s", title, exc)
        return []
