"""Dept-aware rescue for reranker top-K.

Problem: tokenizer splits "전자공학과" -> ["전자", "공학", "과"] so generic
졸업요건 chunks from other depts outscore the real dept body. Reranker
sometimes can't fully recover (e.g. 전자공학과 BM25 #37, 간호학과 BM25 #3,
기계공학부 cross-encoder가 me.cnu.ac.kr 본문을 0.13으로 underscore).

Fix: after rerank, if the query targets a specific dept but the top-K
result has no chunk from that dept's canonical URL host, swap in the
highest-reranked dept-domain chunk from the rest of the pool. This is a
deterministic, low-risk rescue -- only activates when a dept keyword is
detected, and only changes ordering when the dept is missing from top-K.

Promoted chunks are marked with meta["_dept_rescued"] = True so
generate.py can bypass the rerank fallback threshold for them; the dept
host match is a deterministic positive signal even when the cross-encoder
underscores the chunk (e.g. me.cnu.ac.kr 0.13 < threshold 0.15).

Note: 물리(physics.cnu.ac.kr) corpus가 0건이라 rescue 불가. corpus 보강 필요.
"""
from __future__ import annotations

import re
from typing import Sequence

# Pattern: regex on raw query -> canonical URL host to prefer.
DEPT_PATTERNS: dict[str, re.Pattern] = {
    "nursing.cnu.ac.kr": re.compile(r"간호\s*학과|간호\s*학부|간호대학"),
    "ee.cnu.ac.kr": re.compile(r"전자\s*공학(과|부)|전자과(?!공학교육)|전전\b"),
    "me.cnu.ac.kr": re.compile(r"기계\s*공학(부|과)|기공\b|기계과\b"),
    "physics.cnu.ac.kr": re.compile(r"물리\s*학과|물리\s*학부|물리과(?!학교)|물리학\b"),
    "computer.cnu.ac.kr": re.compile(
        r"컴퓨터\s*인공지능|컴퓨터\s*공학|컴공|인공지능학과|인공지능학부"
    ),
    "medicine.cnu.ac.kr": re.compile(r"의예(과)?|의학과"),
    "pharm.cnu.ac.kr": re.compile(r"약학과|약학부|약대\b"),
    "math.cnu.ac.kr": re.compile(r"수학과|수학부|수학교육과"),
    "stat.cnu.ac.kr": re.compile(r"정보\s*통계|통계학과"),
    "ceac.cnu.ac.kr": re.compile(r"응용\s*화학공학|화공\b"),
}


def detect_target_hosts(query: str) -> list[str]:
    """Return list of canonical hosts the query is targeting."""
    if not query:
        return []
    return [host for host, pat in DEPT_PATTERNS.items() if pat.search(query)]


def _chunk_url(c) -> str:
    m = getattr(c, "meta", None) or {}
    return (m.get("source_url") or m.get("_canonical_url") or "").lower()


def _is_target(c, hosts: Sequence[str]) -> bool:
    url = _chunk_url(c)
    return any(h in url for h in hosts)


def rescue(query: str, reranked_full: list, top_k: int = 4) -> list:
    """Return top_k from reranked_full, with dept rescue applied.

    - No dept signal -> reranked_full[:top_k] unchanged.
    - Top_k already contains a dept-host chunk -> unchanged.
    - Otherwise: promote highest-reranked dept-host chunk to #1, drop last.
      Promoted chunk gets meta["_dept_rescued"] = True.
    """
    if not reranked_full:
        return []
    hosts = detect_target_hosts(query)
    if not hosts:
        return reranked_full[:top_k]
    head = list(reranked_full[:top_k])
    if any(_is_target(c, hosts) for c in head):
        return head
    for c in reranked_full[top_k:]:
        if _is_target(c, hosts):
            # mark rescued so generate.py can bypass fallback threshold
            new_meta = dict(c.meta) if c.meta else {}
            new_meta["_dept_rescued"] = True
            c.meta = new_meta
            return [c] + head[:-1]
    return head
