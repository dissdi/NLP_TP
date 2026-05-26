"""Sprint 1 러너 공용 헬퍼.

- 작업 디렉토리 진입 (이 파일 기준 ../ )
- 결과 JSONL 누적 + 진행 로그
- 어댑터 호출 wrapper (에러 무시·진행)
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from contextlib import contextmanager
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import Chunk, write_jsonl  # noqa: E402


def project_root() -> str:
    return _ROOT


def out_path(*parts: str, sprint: str = "sprint1") -> str:
    """data/<sprint>/ 하위에 안전한 경로 생성. sprint default는 backward-compat용."""
    path = os.path.join(_ROOT, "data", sprint, *parts)
    os.makedirs(os.path.dirname(path) or path, exist_ok=True)
    return path


def log_path(day: str, sprint: str = "sprint1") -> str:
    path = os.path.join(_ROOT, "logs", sprint, f"{day}.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


class DayRunner:
    """Day별 러너 컨텍스트.

    사용:
        with DayRunner("day1") as r:
            r.run_a_static(url, domains=[1], categories=["1.1"], title="학사일정")
            r.run_b_paginate(url, domains=[5], categories=["5.4"], pages=5)
            r.run_pdf(url, domains=[4])
            r.dump()

    Sprint 2부터: sprint="sprint2" 인자로 다른 디렉토리에 출력.
    """

    def __init__(self, day: str, sleep: float = 1.2, *, sprint: str = "sprint1"):
        self.day = day
        self.sprint = sprint
        self.client = HttpClient(sleep_between=sleep)
        self.chunks: list[Chunk] = []
        self.errors: list[dict] = []
        self.t0 = time.time()
        self._logf = open(log_path(day, sprint=sprint), "a", encoding="utf-8")

    def __enter__(self):
        self._log(f"\n=== {self.sprint} {self.day} 시작 {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
        return self

    def __exit__(self, exc_type, exc, tb):
        self._log(f"=== {self.day} 종료 {time.time()-self.t0:.1f}s "
                  f"청크={len(self.chunks)} 에러={len(self.errors)} ===")
        self._logf.close()

    def _log(self, msg: str) -> None:
        print(msg)
        try:
            self._logf.write(msg + "\n")
            self._logf.flush()
        except Exception:
            pass

    @contextmanager
    def step(self, label: str):
        self._log(f"\n[step] {label}")
        t0 = time.time()
        try:
            yield
            self._log(f"  ✓ {label}  ({time.time()-t0:.1f}s)")
        except Exception as e:
            tb = traceback.format_exc(limit=4)
            self._log(f"  ✗ {label}  err={type(e).__name__}: {e}\n{tb}")
            self.errors.append({"step": label, "error": str(e), "type": type(e).__name__})

    # ---- 어댑터 호출 wrapper ----

    def run_a_static(
        self,
        url: str,
        *,
        domains: list[int],
        categories: Optional[list[str]] = None,
        title: Optional[str] = None,  # 정보용 — 현재 어댑터 A는 soup.title 사용
    ) -> None:
        """어댑터 A — 정적 HTML 페이지."""
        from crawler.adapters.a_plus import crawl_page  # type: ignore
        label = title or url
        with self.step(f"A:{label}"):
            new = crawl_page(
                url,
                domains=domains,
                categories=categories,
                client=self.client,
            )
            self.chunks.extend(new)
            self._log(f"  + {len(new)} 청크 / {sum(c.char_count for c in new)}자")

    def run_b_paginate(
        self,
        url: str,
        *,
        domains: list[int],
        categories: Optional[list[str]] = None,
        pages: int = 5,
        max_total: Optional[int] = None,
    ) -> None:
        """어댑터 B — 게시판 페이지네이션."""
        from crawler.adapters.b_board import crawl_board_paginated
        with self.step(f"B:{url}  pages={pages}"):
            new = crawl_board_paginated(
                url,
                domains=domains,
                categories=categories,
                max_pages=pages,
                max_posts_total=max_total,
                client=self.client,
            )
            self.chunks.extend(new)
            self._log(f"  + {len(new)} 게시물 / {sum(c.char_count for c in new)}자")

    def run_pdf(
        self,
        url: str,
        *,
        domains: list[int],
        categories: Optional[list[str]] = None,
        title: Optional[str] = None,
        posted_at: Optional[str] = None,
    ) -> None:
        """PDF 파이프라인."""
        from crawler.pdf_pipeline import crawl_pdf
        with self.step(f"PDF:{url}"):
            new, csvs = crawl_pdf(
                url,
                domains=domains,
                categories=categories,
                client=self.client,
                source_title=title,
                posted_at=posted_at,
                table_csv_dir=out_path(self.day, "tables", sprint=self.sprint),
            )
            self.chunks.extend(new)
            self._log(f"  + {len(new)} 청크 / {sum(c.char_count for c in new)}자  "
                      f"표 CSV {len(csvs)}개")

    def run_rule_hwp(
        self,
        url: str,
        *,
        domains: list[int],
        categories: Optional[list[str]] = None,
        max_items: int = 30,
    ) -> None:
        """어댑터 E — 학칙 (javascript onclick → ntt_no → HWP)."""
        from crawler.adapters.e_rule_hwp import crawl_rule_list  # type: ignore
        with self.step(f"RULE_HWP:{url}  max={max_items}"):
            new = crawl_rule_list(
                url, domains=domains, categories=categories,
                max_items=max_items,
                hwp_save_dir=out_path(self.day, "hwp", sprint=self.sprint),
                client=self.client,
            )
            self.chunks.extend(new)
            self._log(f"  + {len(new)} 청크 / {sum(c.char_count for c in new)}자  (학칙)")

    def run_hwp(
        self,
        url: str,
        *,
        domains: list[int],
        categories: Optional[list[str]] = None,
        title: Optional[str] = None,
        prefer: str = "hwp5txt",
    ) -> None:
        """HWP 파이프라인."""
        from crawler.hwp_pipeline import crawl_hwp
        with self.step(f"HWP:{url}"):
            new = crawl_hwp(
                url,
                domains=domains,
                categories=categories,
                client=self.client,
                source_title=title,
                prefer=prefer,
                save_dir=out_path(self.day, "hwp", sprint=self.sprint),
            )
            self.chunks.extend(new)
            self._log(f"  + {len(new)} 청크 / {sum(c.char_count for c in new)}자")

    def dump(self) -> str:
        """결과를 data/<sprint>/<day>/chunks.jsonl 로 저장."""
        path = out_path(self.day, "chunks.jsonl", sprint=self.sprint)
        write_jsonl(self.chunks, path)
        total = sum(c.char_count for c in self.chunks)
        self._log(f"\n=== DUMP {len(self.chunks)} chunks / {total}자 → {path}")
        # 에러 요약
        if self.errors:
            err_path = out_path(self.day, "errors.json", sprint=self.sprint)
            with open(err_path, "w", encoding="utf-8") as f:
                json.dump(self.errors, f, ensure_ascii=False, indent=2)
            self._log(f"=== 에러 {len(self.errors)}건 → {err_path}")
        return path
