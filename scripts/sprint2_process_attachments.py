"""Sprint 2 day별 chunks.jsonl 의 HWP/PDF 첨부 후처리 (sprint1 패턴).

sprint1_process_attachments.py 와 동일 로직. data/sprint2/<day>/chunks.jsonl 만 본다.

실행:
  python -m scripts.sprint2_process_attachments day1
  python -m scripts.sprint2_process_attachments day2 --hwp-prefer libreoffice
  python -m scripts.sprint2_process_attachments day3 --max 30
  python -m scripts.sprint2_process_attachments all
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


SPRINT = "sprint2"
ALL_DAYS = ["day1", "day2", "day3"]


def process_day(day: str, *, hwp_prefer: str, max_n, kinds: set[str]) -> tuple[int, int]:
    src = os.path.join(_ROOT, "data", SPRINT, day, "chunks.jsonl")
    if not os.path.exists(src):
        print(f"[skip] no chunks for {day}: {src}")
        return 0, 0

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
                if max_n is not None and n_proc >= max_n:
                    print(f"[stop] max={max_n} 도달")
                    break
                title = a.get("name") or u
                domains = d.get("domains", [])
                categories = d.get("categories", [])
                parent_url = d.get("source_url") or ""
                posted_at = d.get("posted_at")
                try:
                    if kind == "pdf":
                        from crawler.pdf_pipeline import crawl_pdf
                        new, _ = crawl_pdf(
                            u, domains=domains, categories=categories,
                            client=client, source_title=title, posted_at=posted_at,
                            table_csv_dir=os.path.join(_ROOT, "data", SPRINT, day, "tables"),
                        )
                    elif kind in ("hwp", "hwpx"):
                        from crawler.hwp_pipeline import crawl_hwp
                        new = crawl_hwp(
                            u, domains=domains, categories=categories,
                            client=client, source_title=title, posted_at=posted_at,
                            prefer=hwp_prefer,
                            save_dir=os.path.join(_ROOT, "data", SPRINT, day, "hwp"),
                        )
                    else:
                        new = []
                    for c in new:
                        c.parent_post_id = d.get("parent_post_id") or parent_url[-32:]
                    new_chunks.extend(new)
                    n_proc += 1
                    print(f"[+] {kind} {n_proc}: {title[:60]}  → {len(new)} 청크")
                except Exception as e:
                    print(f"[✗] {kind}: {title[:60]}  err={type(e).__name__}: {e}")

    out = os.path.join(_ROOT, "data", SPRINT, day, "attachments.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_jsonl(new_chunks, out)
    total = sum(c.char_count for c in new_chunks)
    print(f"\n[{day}] OK: {len(new_chunks)} chunks / {total}자 → {out}")
    print(f"          (첨부 {n_total}건 중 {n_proc}건 처리)")
    return len(new_chunks), total


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("day", help="day1~day3 또는 all")
    p.add_argument("--hwp-prefer", default="hwp5txt",
                   choices=["hwp5txt", "libreoffice", "auto"])
    p.add_argument("--max", type=int, default=None, help="day별 처리할 첨부 상한")
    p.add_argument("--kinds", default="hwp,pdf",
                   help="콤마 구분 (hwp/hwpx/pdf 중)")
    args = p.parse_args()

    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    days = ALL_DAYS if args.day == "all" else [args.day]

    grand_n, grand_chars = 0, 0
    for d in days:
        n, ch = process_day(d, hwp_prefer=args.hwp_prefer, max_n=args.max, kinds=kinds)
        grand_n += n
        grand_chars += ch

    print(f"\n=== 합계: {grand_n} chunks / {grand_chars}자")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
