"""PubMed E-utilities 信源（SPEC §5.4，无 key）：仅医学/生物领域触发。"""

from __future__ import annotations

import logging

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA, RateLimiter

log = logging.getLogger(__name__)

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
MEDICAL_DOMAINS = {"医学健康", "自然科学"}
MAX_RESULTS = 10
_LIMITER = RateLimiter(min_interval=0.4)  # NCBI 无 key ≤3 req/s


class PubmedSource:
    name = "pubmed"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        if query.domain and query.domain not in MEDICAL_DOMAINS:
            return []
        try:
            _LIMITER.acquire()
            resp = httpx.get(
                ESEARCH,
                params={
                    "db": "pubmed",
                    "term": query.title,
                    "retmax": MAX_RESULTS,
                    "retmode": "json",
                    "sort": "relevance",
                },
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
            )
            resp.raise_for_status()
            ids = resp.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []
            _LIMITER.acquire()
            resp = httpx.get(
                ESUMMARY,
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
            )
            resp.raise_for_status()
            result = resp.json().get("result", {})
            out: list[Candidate] = []
            for uid in result.get("uids", []):
                doc = result.get(uid, {})
                title = (doc.get("title") or "").rstrip(".")
                if not title:
                    continue
                pages = 0
                prange = (doc.get("pages") or "").replace("e", "")
                if "-" in prange:
                    try:
                        a, b = prange.split("-", 1)
                        pages = max(0, int(b) - int(a) + 1)
                    except ValueError:
                        pass
                out.append(
                    Candidate(
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                        title=title,
                        kind="paper",
                        source=self.name,
                        snippet=doc.get("fulljournalname", ""),
                        lang="en",
                        published=(doc.get("pubdate") or "")[:4],
                        meta={"pages": pages, "journal": doc.get("fulljournalname", "")},
                    )
                )
            return out
        except Exception as exc:
            log.warning("pubmed failed for %s: %s", query.title, exc)
            return []
