"""run_dept_grad_me_phy.sh 의 인라인 -c 블록 대체. discover/crawl 결과 요약."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter


def summarize_candidates(path: str) -> None:
    if not os.path.exists(path):
        print(f"  ⚠ {path} 없음")
        return
    with open(path, encoding="utf-8") as f:
        recs = [json.loads(l) for l in f if l.strip()]
    for r in recs:
        print(f'  {r["dept_name"]}  status={r["status"]}  cand={len(r.get("candidates",[]))}')
        for c in r.get("candidates", [])[:5]:
            print(f'    [{c["score"]}] {c["text"][:50]}  ->  {c["url"]}')


def summarize_chunks(path: str) -> None:
    if not os.path.exists(path):
        print(f"  ⚠ {path} 없음")
        return
    c = Counter()
    sz = Counter()
    url_c = Counter()
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            t = d.get("source_title", "")
            dept = t.split("]")[0].lstrip("[") if "]" in t else "UNKNOWN"
            c[dept] += 1
            sz[dept] += d.get("char_count", 0)
            url_c[d.get("source_url", "")] += 1
            n += 1
    if n == 0:
        print("  ⚠ chunks 0건. direct_url 들이 전부 404 가능. dept_list_me_phy.json 의 direct_url 교체 후 재시도.")
        return
    print("=== 학과별 청크 분포 ===")
    for k in sorted(c):
        print(f"  {k}: {c[k]} chunks, {sz[k]} chars")
    print(f"  TOTAL: {n} chunks, {sum(sz.values())} chars")
    print()
    print("=== source_url 분포 ===")
    for u, cnt in url_c.most_common():
        print(f"  {cnt:>3}  {u}")


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: _summarize_me_phy.py {candidates|chunks} <path>")
        return 2
    mode = sys.argv[1]
    path = sys.argv[2]
    if mode == "candidates":
        summarize_candidates(path)
    elif mode == "chunks":
        summarize_chunks(path)
    else:
        print(f"unknown mode: {mode}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
