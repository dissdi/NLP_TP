"""Rule-based query expansion using a JSON alias dictionary.

For each known alias found in the query (e.g. "컴공", "1학", "포탈"),
append the canonical form. The original query is preserved (so word order,
particles, sentence shape stays natural for the LLM downstream); we only
*add* extra search keywords at the end so BM25 + dense retrieval signals
are stronger.

Usage:
  from crawler.phase_e.query_expand import expand_query
  expanded = expand_query("컴공 졸업하려면?")
  # -> "컴공 졸업하려면? 컴퓨터인공지능학부 컴퓨터공학"
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

_ALIAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aliases.json")


@lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    with open(_ALIAS_PATH, "r", encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_")}


def expand_query(query: str) -> str:
    if not query:
        return query
    aliases = _aliases()
    extras: list[str] = []
    seen: set[str] = set()
    for alias, full in aliases.items():
        if alias in query and full not in query and full not in seen:
            extras.append(full)
            seen.add(full)
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"


if __name__ == "__main__":
    samples = [
        "컴공 졸업하려면 학점 몇 필요해",
        "1학 점심 메뉴 뭐야",
        "포탈에서 휴학 신청 어떻게",
        "졸업요건 학점은 몇 학점인가요",
        "수의 졸업학점",
        "에타 어떻게 가입",
    ]
    for q in samples:
        print(f"  {q!r}")
        print(f"  -> {expand_query(q)!r}")
        print()
