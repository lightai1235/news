"""候选池构建（SPEC §5.1）。

解析维基 Good/Featured articles 与中文典范/优良条目列表的 wikitext，
按标题层级提取领域，经 compliance 过滤后产出 PoolEntry 列表。
网络抓取在 build_pool()；parse_wikitext() 为纯函数，fixtures 可测。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from openmind.compliance import Compliance

log = logging.getLogger(__name__)

UA = "OpenMind/0.1 (daily knowledge digest; +https://github.com/lightai1235/news)"

DOMAINS = (
    "自然科学",
    "数学",
    "技术工程",
    "医学健康",
    "历史",
    "地理",
    "社会",
    "经济商业",
    "哲学宗教",
    "艺术",
    "语言文学",
    "文化生活",
)

SECTION_DOMAIN_MAP = {
    "agriculture": "自然科学",
    "food": "文化生活",
    "drink": "文化生活",
    "art": "艺术",
    "architecture": "艺术",
    "music": "艺术",
    "theatre": "艺术",
    "theater": "艺术",
    "opera": "艺术",
    "dance": "艺术",
    "film": "艺术",
    "biology": "自然科学",
    "medicine": "医学健康",
    "health": "医学健康",
    "chemistry": "自然科学",
    "materials": "技术工程",
    "computing": "技术工程",
    "engineering": "技术工程",
    "technology": "技术工程",
    "transport": "技术工程",
    "earth": "自然科学",
    "geography": "地理",
    "places": "地理",
    "geology": "自然科学",
    "physics": "自然科学",
    "astronomy": "自然科学",
    "space": "自然科学",
    "environment": "自然科学",
    "history": "历史",
    "archaeology": "历史",
    "heraldry": "历史",
    "mathematics": "数学",
    "math": "数学",
    "language": "语言文学",
    "literature": "语言文学",
    "linguistics": "语言文学",
    "philosophy": "哲学宗教",
    "religion": "哲学宗教",
    "mythology": "哲学宗教",
    "psychology": "社会",
    "society": "社会",
    "social": "社会",
    "education": "社会",
    "law": "社会",
    "politics": "社会",
    "government": "社会",
    "military": "社会",
    "warfare": "社会",
    "economics": "经济商业",
    "business": "经济商业",
    "finance": "经济商业",
    "sports": "文化生活",
    "sport": "文化生活",
    "paralympics": "文化生活",
    "olympics": "文化生活",
    "earthquake": "自然科学",
    "disasters in history": "历史",
    "disaster": "自然科学",
    "recreation": "文化生活",
    "television": "文化生活",
    "media": "文化生活",
    "video game history": "技术工程",
    "video game development": "技术工程",
    "電子遊戲硬體": "技术工程",
    "电子游戏硬件": "技术工程",
    "video games": None,
    "数学": "数学",
    "物理": "自然科学",
    "化学": "自然科学",
    "生物": "自然科学",
    "医学": "医学健康",
    "健康": "医学健康",
    "历史": "历史",
    "地理": "地理",
    "技术": "技术工程",
    "工程": "技术工程",
    "计算机": "技术工程",
    "艺术": "艺术",
    "音乐": "艺术",
    "建筑": "艺术",
    "语言": "语言文学",
    "文学": "语言文学",
    "哲学": "哲学宗教",
    "宗教": "哲学宗教",
    "社会": "社会",
    "经济": "经济商业",
    "商业": "经济商业",
    "体育": "文化生活",
    "文化": "文化生活",
    "游戏": None,
    "电子游戏": None,
    "小说": None,
    "动漫": None,
    "藝術": "艺术",
    "建築": "艺术",
    "音樂": "艺术",
    "繪畫": "艺术",
    "生物學": "自然科学",
    "動物": "自然科学",
    "植物": "自然科学",
    "真菌": "自然科学",
    "病毒": "自然科学",
    "化學": "自然科学",
    "礦物": "自然科学",
    "天文": "自然科学",
    "氣象": "自然科学",
    "地球": "自然科学",
    "醫學": "医学健康",
    "藥學": "医学健康",
    "計算機": "技术工程",
    "電腦": "技术工程",
    "資訊": "技术工程",
    "運輸": "技术工程",
    "交通": "技术工程",
    "數學": "数学",
    "歷史": "历史",
    "考古": "历史",
    "語言": "语言文学",
    "文學": "语言文学",
    "哲學": "哲学宗教",
    "神話": "哲学宗教",
    "心理": "社会",
    "社會": "社会",
    "教育": "社会",
    "法律": "社会",
    "政治": "社会",
    "軍事": "社会",
    "戰爭": "社会",
    "經濟": "经济商业",
    "商業": "经济商业",
    "金融": "经济商业",
    "體育": "文化生活",
    "運動": "文化生活",
    "傳媒": "文化生活",
    "媒體": "文化生活",
    "遊戲": None,
    "電子遊戲": None,
    "小說": None,
    "動漫": None,
}

_LINK_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]*)?\]\]")
_HEADING_RE = re.compile(r"^(={2,4})\s*(.+?)\s*\1\s*$", re.MULTILINE)
_TRANSCLUSION_RE = re.compile(r"\{\{([^{}|]+)(?:\|[^{}]*)?\}\}")

TOPIC_PREFIXES = (
    "Wikipedia:Good articles/",
    "Wikipedia:Featured articles/",
    "Wikipedia:优良条目/分类/",
    "Wikipedia:典範條目/",
    "Wikipedia:典范条目/",
)
_NON_ARTICLE_PREFIXES = (
    "wikipedia:",
    "file:",
    "image:",
    "category:",
    "template:",
    "help:",
    "special:",
    "portal:",
    "talk:",
    "user:",
    "mediawiki:",
    "module:",
    "draft:",
    "wikt:",
    "w:",
    "s:",
    "#",
)
TRANSCLUDE_MAX_PAGES = 300


@dataclass
class PoolEntry:
    canonical_title: str
    lang: str
    domain: str
    section: str


# 长键优先：避免 "history" 抢先命中 "Video game history and development"
_SORTED_MAP_KEYS = sorted(SECTION_DOMAIN_MAP, key=len, reverse=True)
# 短英文键按整词匹配，防止 "art" 命中 "Paralympics"/"particles" 等子串
_WORD_BOUNDARY_KEYS = {k for k in SECTION_DOMAIN_MAP if k.isascii() and len(k) <= 5}
_KEY_PATTERNS = {
    k: (re.compile(r"\b" + re.escape(k) + r"\b") if k in _WORD_BOUNDARY_KEYS else None)
    for k in SECTION_DOMAIN_MAP
}


def _key_hits(key: str, low: str) -> bool:
    pat = _KEY_PATTERNS[key]
    return bool(pat.search(low)) if pat is not None else key in low


def _map_domain(section: str) -> str | None:
    low = section.lower()
    for key in _SORTED_MAP_KEYS:
        if _key_hits(key, low):
            return SECTION_DOMAIN_MAP[key]
    return None


def _map_domain_chain(section_chain: list[str]) -> str | None:
    # 自叶向根取第一个命中的映射（含显式 None 排除，如 Video games 作品区）
    for sec in reversed(section_chain):
        low = sec.lower()
        for key in _SORTED_MAP_KEYS:
            if _key_hits(key, low):
                return SECTION_DOMAIN_MAP[key]
    return None


# 虚构作品分区（SPEC §5.5 条目级排除）：分区内条目是电影/剧集/小说/歌曲等作品本体。
# 现实研究分区（电影史、游戏史、音乐理论、电视台概述等）不在此列，保留。
# 注意 "games" 裸词会误伤 "Olympic games"，只匹配 "video game"。
FICTION_SECTION_KEYWORDS = (
    "film",  # 含 Films / 1910s films / 2010 to 2014 films；现实研究由白名单放行
    "film series",
    "television series",
    "television shows",
    "television seasons",
    "episodes of television",
    "fictional character",
    "novels",
    "short stories",
    "albums",
    "songs",
    "video game",
    "遊戲",
    "游戏",
    "小说",
    "小說",
    "动漫",
    "動漫",
    "虚构",
    "虛構",
    "文學作品",
    "文学作品",
    "媒體作品",
    "媒体作品",
    "流行音樂歌曲",
    "流行音樂專輯",
)
# 分区含上述作品关键词但属现实研究主题的白名单（优先于排除判定）
REALITY_SECTION_KEYWORDS = (
    "history",
    "development",
    "overview",
    "production",
    "franchises",
    "networks",
    "theory",
    "genres",
    "techniques",
    "hardware",
    "硬體",
    "硬件",
    "文化",
    "非虚构",
    "非虛構",
    "非文學",
)
# 斜体包裹的具名作品分区（如 ''Law & Order'' series / ''Kingdom Hearts'' characters）
_ITALIC_SECTION_RE = re.compile(r"''[^']+''")


def _is_fiction_section(section: str) -> bool:
    low = section.lower()
    if any(k in low for k in REALITY_SECTION_KEYWORDS):
        return False
    if _ITALIC_SECTION_RE.search(section):
        return True
    return any(k in low for k in FICTION_SECTION_KEYWORDS)


_NOTE_TA_RE = re.compile(r"-\{.*?\}-", re.DOTALL)


def _strip_note_ta(text: str) -> str:
    """剥离中文 noteTA 变体标记 -{...}-（内部可能嵌套链接，会截断匹配）。"""
    return _NOTE_TA_RE.sub("", text)


def extract_transclusions(text: str) -> list[str]:
    """提取主题子页面转录（排除 Summary/Tab header 等辅助模板与参数）。"""
    out: list[str] = []
    for m in _TRANSCLUSION_RE.finditer(text):
        name = m.group(1).strip()
        if name.startswith(TOPIC_PREFIXES) and name not in out:
            out.append(name)
    return out


def parse_wikitext(
    text: str, lang: str, comp: Compliance, default_section: str = ""
) -> list[PoolEntry]:
    text = _strip_note_ta(text)
    entries: list[PoolEntry] = []
    seen: set[str] = set()
    section = default_section
    excluded_section = False
    events: list[tuple[int, str, str]] = []
    for m in _HEADING_RE.finditer(text):
        events.append((m.start(), "heading", m.group(2), len(m.group(1))))
    for m in _LINK_RE.finditer(text):
        events.append((m.start(), "link", m.group(1).strip(), 0))
    events.sort(key=lambda e: e[0])

    # 分区层级栈：领域映射与虚构排除都沿父链判定
    # （如 ====20th Century==== 本身无关键词，但父分区 ===Films=== 是虚构作品区）
    chain: list[tuple[int, str]] = [(1, default_section)] if default_section else []
    for _, kind, value, level in events:
        if kind == "heading":
            if value.lower() in ("ga", "contents", "back", "continue", "see also", "notes", "map"):
                continue
            while chain and chain[-1][0] >= level:
                chain.pop()
            chain.append((level, value))
            section = value
            excluded_section = any(_is_fiction_section(s) for _, s in chain)
            continue
        if excluded_section:
            continue
        title = value
        if title in seen or title.lower().startswith(_NON_ARTICLE_PREFIXES):
            continue
        ok, _reason = comp.check_entry(title, categories=[])
        if not ok:
            continue
        domain = _map_domain_chain([s for _, s in chain])
        if domain is None:
            continue
        seen.add(title)
        entries.append(PoolEntry(canonical_title=title, lang=lang, domain=domain, section=section))
    return entries


def _fetch_wikitext(api: str, page: str, client: httpx.Client) -> str:
    resp = client.get(
        api,
        params={
            "action": "parse",
            "page": page,
            "prop": "wikitext",
            "format": "json",
            "formatversion": 2,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["parse"]["wikitext"]


def _crawl(
    api: str,
    page: str,
    lang: str,
    comp: Compliance,
    client: httpx.Client,
    budget: list[int],
    default_section: str = "",
) -> list[PoolEntry]:
    """递归抓取：索引页展开转录子页面，叶子页解析条目链接。"""
    if budget[0] <= 0:
        return []
    budget[0] -= 1
    text = _fetch_wikitext(api, page, client)
    time.sleep(0.5)
    entries = parse_wikitext(text, lang=lang, comp=comp, default_section=default_section)
    section = default_section or page.split("/")[-1]
    for sub in extract_transclusions(text):
        if budget[0] <= 0:
            log.warning("transclusion budget exhausted at %s", page)
            break
        try:
            entries.extend(_crawl(api, sub, lang, comp, client, budget, default_section=section))
        except Exception as exc:
            log.warning("subpage %s failed: %s", sub, exc)
    return entries


def build_pool(state_dir: Path, refresh: bool = False) -> list[PoolEntry]:
    pool_path = state_dir / "pool.json"
    if pool_path.exists() and not refresh:
        data = json.loads(pool_path.read_text(encoding="utf-8"))
        age_days = (time.time() - data.get("built_at", 0)) / 86400
        if age_days < 7:
            return [PoolEntry(**e) for e in data["entries"]]

    comp = Compliance.load(state_dir)
    entries: list[PoolEntry] = []
    sources = [
        ("https://en.wikipedia.org/w/api.php", "Wikipedia:Good articles/all", "en"),
        ("https://en.wikipedia.org/w/api.php", "Wikipedia:Good articles/all2", "en"),
        ("https://en.wikipedia.org/w/api.php", "Wikipedia:Featured articles", "en"),
        ("https://zh.wikipedia.org/w/api.php", "Wikipedia:典范条目", "zh"),
        ("https://zh.wikipedia.org/w/api.php", "Wikipedia:优良条目", "zh"),
    ]
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        for api, page, lang in sources:
            try:
                got = _crawl(api, page, lang, comp, client, budget=[TRANSCLUDE_MAX_PAGES])
                log.info("pool source %s: %d entries", page, len(got))
                entries.extend(got)
            except Exception as exc:
                log.warning("pool source %s failed: %s", page, exc)
            time.sleep(1.0)

    merged: dict[str, PoolEntry] = {}
    for e in entries:
        merged.setdefault(e.canonical_title, e)
    result = list(merged.values())
    if not result:
        log.warning("all pool sources failed; keeping existing pool.json untouched")
        if pool_path.exists():
            data = json.loads(pool_path.read_text(encoding="utf-8"))
            return [PoolEntry(**e) for e in data["entries"]]
        return []
    state_dir.mkdir(parents=True, exist_ok=True)
    pool_path.write_text(
        json.dumps(
            {"built_at": time.time(), "entries": [asdict(e) for e in result]}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    log.info("pool built: %d entries", len(result))
    return result
