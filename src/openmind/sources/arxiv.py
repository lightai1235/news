"""arXiv API 信源（SPEC §5.4，无 key）：一手论文，Atom XML。"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA

log = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
MAX_RESULTS = 10


class ArxivSource:
    name = "arxiv"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        try:
            resp = httpx.get(
                ARXIV_API,
                params={
                    "search_query": f'all:"{query.title}"',
                    "start": 0,
                    "max_results": MAX_RESULTS,
                },
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
            )
            resp.raise_for_status()
            return self._parse(resp.text, query)
        except Exception as exc:
            log.warning("arxiv failed for %s: %s", query.title, exc)
            return []

    def _parse(self, xml_text: str, query: Query) -> list[Candidate]:
        root = ET.fromstring(xml_text)
        out: list[Candidate] = []
        for entry in root.findall(f"{_ATOM}entry"):
            title = (entry.findtext(f"{_ATOM}title") or "").strip()
            url = (entry.findtext(f"{_ATOM}id") or "").strip()
            if not title or not url:
                continue
            summary = re.sub(r"\s+", " ", entry.findtext(f"{_ATOM}summary") or "").strip()
            published = (entry.findtext(f"{_ATOM}published") or "")[:10]
            comment = entry.findtext(f"{_ARXIV}comment") or ""
            pages = 0
            m = re.search(r"(\d+)\s*pages", comment)
            if m:
                pages = int(m.group(1))
            out.append(
                Candidate(
                    url=url.replace("http://", "https://"),
                    title=title,
                    kind="paper",
                    source=self.name,
                    snippet=summary[:500],
                    lang="en",
                    published=published,
                    meta={"pages": pages} if pages else {},
                )
            )
        return out
