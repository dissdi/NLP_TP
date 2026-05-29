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

# Hangul syllable block: U+AC00 ~ U+D7A3
_HANGUL_START = "가"
_HANGUL_END = "힣"


@lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    with open(_ALIAS_PATH, "r", encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _matches_alias(alias: str, query: str) -> bool:
    """Return True if alias occurs in query at a valid (boundary) position.

    For digit-prefixed aliases (e.g. '1학', '2학', '3학', '4학') a match is
    only accepted when the character immediately after the alias is NOT a
    Hangul syllable.  This prevents false expansions such as:

        '1학기 수강신청'  -> '1학' matches -> injects '제1학생회관'  [BAD]
        '1학 메뉴 뭐야'  -> '1학' matches -> injects '제1학생회관'  [OK]

    All occurrences of the alias in the query are checked; the first valid
    occurrence is sufficient.  Non-digit aliases are matched as before (plain
    substring check), since they are complete morphological units that do not
    tend to be spurious prefixes of other words.
    """
    if alias not in query:
        return False
    if not alias or not alias[0].isdigit():
        # Non-digit alias: plain substring match is fine
        return True
    # Digit-prefixed alias: require that the match is NOT followed by Hangul
    a_len = len(alias)
    start = 0
    while True:
        idx = query.find(alias, start)
        if idx == -1:
            return False
        end = idx + a_len
        if end >= len(query) or not (_HANGUL_START <= query[end] <= _HANGUL_END):
            return True  # valid occurrence found
        start = idx + 1


def expand_query(query: str) -> str:
    if not query:
        return query
    aliases = _aliases()
    extras: list[str] = []
    seen: set[str] = set()
    for alias, full in aliases.items():
        if _matches_alias(alias, query) and full not in query and full not in seen:
            extras.append(full)
            seen.add(full)
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"


if __name__ == "__main__":
    # Regression tests for the digit-alias boundary fix (A2-aliases-clean)
    ok_cases = [
        # (query, should_contain_in_expansion, comment)
        ("1학 점심 메뉴 뭐야",         "제1학생회관", "1학 standalone -> expand OK"),
        ("2학 식당 뭐임",              "제2학생회관", "2학 standalone -> expand OK"),
        ("1학기에 1학 식당 가고 싶어", "제1학생회관", "1학기 first but 1학 later -> OK"),
    ]
    bad_cases = [
        # (query, must_NOT_contain_in_expansion, comment)
        ("1학기 수강신청 방법",   "제1학생회관", "1학기 -> must NOT expand"),
        ("2학기 성적 확인",       "제2학생회관", "2학기 -> must NOT expand"),
        ("3학년 필수과목",        "제3학생회관", "3학년 -> must NOT expand"),
        ("4학기 수업 일정",       "제4학생회관", "4학기 -> must NOT expand"),
    ]
    general_cases = [
        ("컴공 졸업하려면 학점 몇 필요해", None, "컴공 -> expand"),
        ("포탈에서 휴학 신청 어떻게",      None, "포탈+휴학"),
        ("졸업요건 학점은 몇 학점인가요",   None, "no alias -> unchanged"),
    ]

    all_pass = True
    print("=== A2 boundary-fix regression tests ===\n")
    for q, expected, comment in ok_cases:
        result = expand_query(q)
        ok = expected in result
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {comment}")
        print(f"         in : {q!r}")
        print(f"         out: {result!r}\n")

    for q, must_not, comment in bad_cases:
        result = expand_query(q)
        ok = must_not not in result
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {comment}")
        print(f"         in : {q!r}")
        print(f"         out: {result!r}\n")

    for q, _, comment in general_cases:
        result = expand_query(q)
        print(f"  [INFO] {comment}")
        print(f"         in : {q!r}")
        print(f"         out: {result!r}\n")

    print("=== Result:", "ALL PASS" if all_pass else "SOME FAIL", "===")
