"""D-1 청크 샘플링: 도메인별 + URL/제목 키워드 보완으로 후보 pool 생성.

입력: data/phase_c/03_enriched/corpus/all.jsonl
출력: eval/_workspace/pool_d{1..9}.jsonl
"""
from __future__ import annotations
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "phase_c" / "03_enriched" / "corpus" / "all.jsonl"
OUT_DIR = ROOT / "eval" / "_workspace"
OUT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)

# 도메인별 보조 분류 규칙 (URL host + title keyword)
DOMAIN_RULES = {
    1: {  # 학사
        "hosts": ["plus.cnu.ac.kr"],
        "url_kw": ["sub05", "academic", "haksa", "교과", "학사"],
        "title_kw": ["학사", "수강", "교과", "학적", "졸업", "성적", "전과", "복학", "휴학"],
    },
    2: {  # 식생활
        "hosts": ["co-op.cnu.ac.kr", "coop.cnu.ac.kr"],
        "url_kw": ["sikdan", "식단", "menu"],
        "title_kw": ["식단", "학식", "생협", "식당", "메뉴", "식권"],
    },
    3: {  # 도서관
        "hosts": ["library.cnu.ac.kr", "lib.cnu.ac.kr"],
        "url_kw": ["library"],
        "title_kw": ["도서관", "대출", "열람", "자료실", "ILL", "원문복사"],
    },
    4: {  # 기숙사
        "hosts": ["dorm.cnu.ac.kr"],
        "url_kw": ["dorm", "기숙"],
        "title_kw": ["기숙사", "생활관", "입사", "퇴사", "사생", "호실"],
    },
    5: {  # 학생활동·공지
        "hosts": ["plus.cnu.ac.kr"],
        "url_kw": ["notice", "bbs", "공지", "활동"],
        "title_kw": ["공지", "안내", "동아리", "학생회", "행사", "활동", "이벤트"],
    },
    6: {  # 장학·등록금
        "hosts": ["plus.cnu.ac.kr"],
        "url_kw": ["scholar", "장학", "tuition", "등록"],
        "title_kw": ["장학", "등록금", "납부", "감면", "면제", "학자금"],
    },
    7: {  # 진로·취업
        "hosts": ["cli.cnu.ac.kr", "plus.cnu.ac.kr"],
        "url_kw": ["career", "job", "취업", "진로"],
        "title_kw": ["취업", "진로", "인턴", "채용", "career", "구직", "직무"],
    },
    8: {  # 행정·증명서
        "hosts": ["plus.cnu.ac.kr"],
        "url_kw": ["jeungmyeong", "certificate"],
        "title_kw": ["증명서", "발급", "학생증", "민원", "재학증명", "성적증명"],
    },
    9: {  # 캠퍼스 생활·시설
        "hosts": ["gymn.cnu.ac.kr", "health.cnu.ac.kr"],
        "url_kw": ["facility", "health", "shuttle"],
        "title_kw": ["보건", "체육", "셔틀", "편의", "복지", "주차", "시설", "휴게"],
    },
}

# 외부 통계 호스트 (도메인 D 타입에 활용)
ACADEMYINFO_HOST = "www.academyinfo.go.kr"


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def chunk_matches_domain(chunk: dict, d: int) -> int:
    """0=no match, 1=meta match, 2=keyword match, 3=both."""
    score = 0
    domains = chunk.get("domains") or []
    if d in domains:
        score |= 1
    rule = DOMAIN_RULES[d]
    host = host_of(chunk.get("source_url", ""))
    url_l = (chunk.get("source_url") or "").lower()
    title_l = (chunk.get("source_title") or "")
    if any(h in host for h in rule["hosts"]):
        score |= 2
    if any(kw in url_l for kw in rule["url_kw"]):
        score |= 2
    if any(kw in title_l for kw in rule["title_kw"]):
        score |= 2
    return score


def good_text_score(text: str) -> int:
    """Q&A 생성 적합성: 길이 + 정보밀도 휴리스틱."""
    if not text:
        return 0
    n = len(text)
    if n < 80:
        return 0
    score = 0
    # 숫자/날짜/기호 풍부함 (사실 Q에 좋음)
    if re.search(r"\d{4}", text):
        score += 2
    if re.search(r"\d+(시간|일|원|만원|점|학점|학기|년)", text):
        score += 2
    # 단계/번호 (절차 Q에 좋음)
    if re.search(r"(\d+\.|①|②|③|첫째|둘째|단계)", text):
        score += 2
    # 너무 단순한 navigation 페이지 패널티
    nav_markers = ["TAB MENU", "본문 바로가기", "주메뉴 바로가기", "검색분류선택"]
    nav_hit = sum(1 for m in nav_markers if m in text)
    score -= nav_hit
    # 적당한 길이 보너스
    if 200 <= n <= 1500:
        score += 3
    elif n > 1500:
        score += 1
    return score


def main():
    chunks = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"loaded {len(chunks)} chunks")

    # 도메인 7 D 타입 (취업통계)은 academyinfo D-통계 청크가 필요
    by_domain = defaultdict(list)
    for c in chunks:
        for d in range(1, 10):
            m = chunk_matches_domain(c, d)
            if m > 0:
                ts = good_text_score(c.get("text", ""))
                if ts <= 0:
                    continue
                by_domain[d].append((m * 5 + ts, c))

    # 학과 D-통계 (취업률) 별도 도메인 7 보강
    for c in chunks:
        if host_of(c.get("source_url", "")) == ACADEMYINFO_HOST:
            text = c.get("text", "")
            if "취업률" in text or "취업자" in text or "졸업생" in text:
                by_domain[7].append((20, c))

    # 도메인별 pool dedup + 점수 정렬
    summary = []
    for d in range(1, 10):
        items = by_domain[d]
        # dedup by chunk_id
        seen = set()
        deduped = []
        for s, c in sorted(items, key=lambda x: -x[0]):
            cid = c.get("chunk_id")
            if cid in seen:
                continue
            seen.add(cid)
            deduped.append((s, c))
        # 도메인별 pool size 상한 (sparse는 모두, dense는 상위 80)
        cap = 80 if len(deduped) > 80 else len(deduped)
        pool = deduped[:cap]
        out = OUT_DIR / f"pool_d{d}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for s, c in pool:
                # 출력 시 score 포함 + text는 1500자 truncate
                rec = dict(c)
                rec["_pool_score"] = s
                if rec.get("text") and len(rec["text"]) > 1500:
                    rec["text"] = rec["text"][:1500] + " ...[truncated]"
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        summary.append((d, len(deduped), len(pool)))
        print(f"d{d}: total_candidates={len(deduped)}, pool_written={len(pool)}")

    # 통계 저장
    stat_path = OUT_DIR / "pool_summary.md"
    with stat_path.open("w", encoding="utf-8") as f:
        f.write("# D-1 청크 pool 요약\n\n")
        f.write(f"corpus: {CORPUS.relative_to(ROOT)}\n\n")
        f.write("| 도메인 | 후보 총수 | pool 크기 |\n|---|---|---|\n")
        for d, n, p in summary:
            f.write(f"| d{d} | {n} | {p} |\n")
    print(f"summary -> {stat_path}")


if __name__ == "__main__":
    main()
