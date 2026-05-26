"""Day 4(또는 임의 day) 결과의 HWP/PDF 첨부 후처리.

어댑터 B는 게시물 본문 + 첨부 메타(URL·확장자)를 Chunk.notes에 JSON으로 저장한다.
이 스크립트는:
  1. data/sprint1/<day>/chunks.jsonl 을 읽어
  2. notes에 attachments가 있는 청크를 모아
  3. HWP는 hwp_pipeline로, PDF는 pdf_pipeline로 다운로드·파싱
  4. 새 청크를 data/sprint1/<day>/attachments.jsonl 로 별도 저장

학칙(1.3)·기숙사 4.4·셔틀 9.1 등 본문이 첨부에 있는 케이스 처리에 사용.

실행:
  python -m scripts.sprint1_process_attachments day4
  python -m scripts.sprint1_process_attachments day4 --hwp-prefer libreoffice
  python -m scripts.sprint1_process_attachments day4 --max 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import write_jsonl  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("day", help="day1~day5")
    p.add_argument("--hwp-prefer", default="hwp5txt",
                   choices=["hwp5txt", "libreoffice", "auto"])
    p.add_argument("--max", type=int, default=None, help="처리할 첨부 상한")
    p.add_argument("--kinds", default="hwp,pdf",
                   help="콤마 구분 (hwp/hwpx/pdf 중)")
    args = p.parse_args()

    src = os.path.join(_ROOT, "data", "sprint1", args.day, "chunks.jsonl")
    if not os.path.exists(src):
        print(f"ERR: 입력 파일 없음: {src}", file=sys.stderr)
        return 2

    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    client = HttpClient(sleep_between=1.0)
    new_chunks = []
    seen_atch_urls: set[str] = set()
    n_total = 0
    n_proc = 0

    with open(src, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            notes = d.get("notes")
            if not notes:
                continue
            try:
                nobj = json.loads(notes)
            except Exception:
                continue
            atts = nobj.get("attachments") or []
            for a in atts:
                kind = a.get("kind")
                if kind not in kinds:
                    continue
                u = a["url"]
                if u in seen_atch_urls:
                    continue
                seen_atch_urls.add(u)
                n_total += 1
                if args.max is not None and n_proc >= args.max:
                    print(f"[stop] max={args.max} 도달")
                    break
                title = a.get("name") or u
                domains = d.get("domains", [])
                categories = d.get("categories", [])
                parent_url = d.get("source_url")
                posted_at = d.get("posted_at")
                try:
                    if kind == "pdf":
                        from crawler.pdf_pipeline import crawl_pdf
                        new, _ = crawl_pdf(
                            u,
                            domains=domains,
                            categories=categories,
                            client=client,
                            source_title=title,
                            posted_at=posted_at,
                            table_csv_dir=os.path.join(
                                _ROOT, "data", "sprint1", args.day, "tables"
                            ),
                        )
                    elif kind in ("hwp", "hwpx"):
                        from crawler.hwp_pipeline import crawl_hwp
                        new = crawl_hwp(
                            u,
                            domains=domains,
                            categories=categories,
                            client=client,
                            source_title=title,
                            posted_at=posted_at,
                            prefer=args.hwp_prefer,
                            save_dir=os.path.join(
                                _ROOT, "data", "sprint1", args.day, "hwp"
                            ),
                        )
                    else:
                        new = []
                    # parent_post_id에 게시물 URL 시그널 남김
                    for c in new:
                        c.parent_post_id = (
                            d.get("parent_post_id") or parent_url[-32:]
                        )
                    new_chunks.extend(new)
                    n_proc += 1
                    print(f"[+] {kind} {n_proc}: {title[:60]}  → {len(new)} 청크")
                except Exception as e:
                    print(f"[✗] {kind}: {title[:60]}  err={type(e).__name__}: {e}")

    out = os.path.join(_ROOT, "data", "sprint1", args.day, "attachments.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_jsonl(new_chunks, out)
    total = sum(c.char_count for c in new_chunks)
    print(f"\nOK: {len(new_chunks)} chunks / {total}자 → {out}")
    print(f"     (첨부 {n_total}건 중 {n_proc}건 처리)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
