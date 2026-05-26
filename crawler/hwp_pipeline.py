"""HWP 파이프라인 — 한글 워드 문서 처리.

Sprint 0에서 발견된 cross-cutting 이슈:
  - 학칙·규정 전체가 HWP 전용 (plus.cnu.ac.kr/_prog/rule/)
  - 백마광장 게시판 첨부 다수가 HWP

두 경로 모두 지원해서 사용자가 환경에 맞게 선택:
  (a) LibreOffice CLI → PDF → pdfplumber  ─ 표 구조 일부 보존 (~70% 신뢰)
  (b) hwp5txt (pyhwp 패키지)               ─ 순수 텍스트 (~80% 신뢰, 표 손실)
  (c) 수동 변환                              ─ 1회성 (학칙 권장)

자동 폴백 순서: (b) → (a). 둘 다 실패하면 명확한 에러.

CLI:
  spike  URL_OR_PATH       # (a)·(b) 둘 다 돌려 결과 비교
  inspect URL_OR_PATH      # 메타·길이 진단
  crawl   URL_OR_PATH ...  # 텍스트 청크 저장
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import Chunk, write_jsonl  # noqa: E402


# --------------------------------------------------------------------------- #
# 다운로드 / 캐시 — pdf_pipeline.py 와 동일 패턴
# --------------------------------------------------------------------------- #

HWP_MAGIC = b"\xD0\xCF\x11\xE0"  # CFB (HWP 5.x compound binary) — DOC와 공유
HWP_MAGIC_HWPX = b"PK\x03\x04"   # HWPX = zip


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _safe_filename(url_or_path: str) -> str:
    base = os.path.basename(urlparse(url_or_path).path) or "document.hwp"
    base = re.sub(r"[^\w\-_.가-힣]", "_", base)
    return base


def _is_valid_hwp(path: str) -> tuple[bool, str]:
    """파일이 HWP(5.x)·HWPX인지 magic number로 확인. (ok, kind)."""
    if not os.path.exists(path) or os.path.getsize(path) < 8:
        return False, "missing"
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(HWP_MAGIC):
        return True, "hwp5"
    if head.startswith(HWP_MAGIC_HWPX):
        return True, "hwpx"
    return False, head[:4].hex()


def download_hwp(
    url: str,
    save_dir: str = "data/sprint1/hwp",
    client: Optional[HttpClient] = None,
) -> str:
    """HWP/HWPX 다운로드 후 로컬 경로 반환. 캐시 검증 포함."""
    client = client or HttpClient()
    os.makedirs(save_dir, exist_ok=True)
    fname = _safe_filename(url)
    if not fname.lower().endswith((".hwp", ".hwpx")):
        fname += ".hwp"
    path = os.path.join(save_dir, fname)

    if os.path.exists(path):
        ok, kind = _is_valid_hwp(path)
        if ok:
            print(f"[cache] {path} ({kind})")
            return path
        os.remove(path)

    data = client.get_bytes(url)
    if not (data.startswith(HWP_MAGIC) or data.startswith(HWP_MAGIC_HWPX)):
        head_preview = data[:64].decode("utf-8", errors="replace")
        raise ValueError(
            f"Response is not HWP/HWPX (first 64 bytes: {head_preview!r}). "
            f"URL may be a page link rather than a direct download endpoint. URL: {url}"
        )
    # HWPX인데 .hwp 확장자였다면 교정
    if data.startswith(HWP_MAGIC_HWPX) and not path.lower().endswith(".hwpx"):
        path = path[:-4] + ".hwpx" if path.lower().endswith(".hwp") else path + "x"
    with open(path, "wb") as f:
        f.write(data)
    print(f"[downloaded] {len(data)} bytes → {path}")
    return path


# --------------------------------------------------------------------------- #
# (b) hwp5txt 경로 — pyhwp 패키지의 CLI
# --------------------------------------------------------------------------- #

def extract_with_hwp5txt(path: str) -> Optional[str]:
    """`hwp5txt <path>` 실행. pyhwp가 설치돼 있어야 함. HWPX는 지원 안 됨.

    Returns:
        추출된 텍스트 (성공) / None (실행 실패)
    """
    if shutil.which("hwp5txt") is None:
        return None
    if path.lower().endswith(".hwpx"):
        # pyhwp는 HWP 5.x 전용
        return None
    try:
        r = subprocess.run(
            ["hwp5txt", path],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            print(f"[hwp5txt rc={r.returncode}] stderr: {r.stderr[:200]}", file=sys.stderr)
            return None
        return r.stdout
    except Exception as e:
        print(f"[hwp5txt error] {e}", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# (a) LibreOffice → PDF → pdfplumber 경로
# --------------------------------------------------------------------------- #

def _find_soffice() -> Optional[str]:
    """LibreOffice 실행 파일 탐색. Linux/macOS는 'soffice', Windows는 'soffice.exe'."""
    for cand in ("soffice", "libreoffice", "soffice.exe"):
        p = shutil.which(cand)
        if p:
            return p
    # macOS 기본 경로
    for cand in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
    ):
        if os.path.exists(cand):
            return cand
    return None


def convert_hwp_to_pdf(hwp_path: str, out_dir: str) -> Optional[str]:
    """soffice --convert-to pdf <hwp> --outdir <dir>.

    Returns:
        생성된 PDF 경로 (성공) / None (실패)
    """
    soffice = _find_soffice()
    if soffice is None:
        return None
    os.makedirs(out_dir, exist_ok=True)
    try:
        r = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf",
             "--outdir", out_dir, hwp_path],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            print(f"[soffice rc={r.returncode}] {r.stderr[:200]}", file=sys.stderr)
            return None
        base = os.path.splitext(os.path.basename(hwp_path))[0] + ".pdf"
        pdf_path = os.path.join(out_dir, base)
        return pdf_path if os.path.exists(pdf_path) else None
    except Exception as e:
        print(f"[soffice error] {e}", file=sys.stderr)
        return None


def extract_with_libreoffice(hwp_path: str) -> tuple[Optional[str], Optional[str]]:
    """LibreOffice→PDF→pdfplumber 경로.

    Returns:
        (extracted_text, pdf_path)
    """
    import pdfplumber  # 지연 import (HWP만 쓰는 사용자 부담 ↓)

    with tempfile.TemporaryDirectory() as td:
        pdf = convert_hwp_to_pdf(hwp_path, td)
        if pdf is None:
            return None, None
        try:
            with pdfplumber.open(pdf) as p:
                buf = []
                for pg in p.pages:
                    t = pg.extract_text() or ""
                    if t.strip():
                        buf.append(t)
                # PDF 자체는 보존(품질 검증·표 추출 용도)
                preserved = os.path.join(
                    os.path.dirname(hwp_path),
                    os.path.splitext(os.path.basename(hwp_path))[0] + ".converted.pdf",
                )
                shutil.copyfile(pdf, preserved)
                return "\n\n".join(buf), preserved
        except Exception as e:
            print(f"[pdfplumber error] {e}", file=sys.stderr)
            return None, None


# --------------------------------------------------------------------------- #
# 통합 추출 — 자동 폴백 (b → a)
# --------------------------------------------------------------------------- #

@dataclass
class HwpExtractResult:
    text: Optional[str]
    method: str           # "hwp5txt" / "libreoffice" / "none"
    pdf_path: Optional[str] = None
    notes: Optional[str] = None


def extract_hwp(path: str, prefer: str = "hwp5txt") -> HwpExtractResult:
    """HWP 텍스트 추출. prefer 우선 시도 후 폴백.

    prefer in {"hwp5txt", "libreoffice", "auto"}.
    auto = hwp5txt 먼저, 없거나 짧으면 libreoffice 시도.
    """
    text: Optional[str] = None
    method = "none"
    pdf_path: Optional[str] = None

    order = []
    if prefer == "libreoffice":
        order = ["libreoffice", "hwp5txt"]
    else:
        order = ["hwp5txt", "libreoffice"]

    for m in order:
        if m == "hwp5txt":
            t = extract_with_hwp5txt(path)
            if t and len(t.strip()) > 30:
                text, method = t, "hwp5txt"
                break
        elif m == "libreoffice":
            t, pdf = extract_with_libreoffice(path)
            if t and len(t.strip()) > 30:
                text, method, pdf_path = t, "libreoffice", pdf
                break

    return HwpExtractResult(text=text, method=method, pdf_path=pdf_path)


# --------------------------------------------------------------------------- #
# spike — (a)·(b) 양쪽 결과 비교
# --------------------------------------------------------------------------- #

def spike(source: str, client: Optional[HttpClient] = None) -> None:
    """샘플 HWP 1개로 (a)·(b) 모두 시도하고 결과 비교."""
    local = download_hwp(source, client=client) if _is_url(source) else source
    print(f"\n=== HWP SPIKE: {local} ===")
    ok, kind = _is_valid_hwp(local)
    print(f"magic: ok={ok} kind={kind}  size={os.path.getsize(local)} bytes")

    # (b) hwp5txt
    print("\n--- (b) hwp5txt ---")
    t_b = extract_with_hwp5txt(local)
    if t_b is None:
        print("  ✗ 실행 실패 또는 pyhwp 미설치 (HWPX는 미지원)")
        print("  설치: pip install pyhwp  → `hwp5txt` 명령 사용 가능")
    else:
        print(f"  ✓ {len(t_b)}자 추출")
        print(f"  preview: {t_b[:300].strip()}…")

    # (a) LibreOffice
    print("\n--- (a) LibreOffice → PDF → pdfplumber ---")
    soffice = _find_soffice()
    if soffice is None:
        print("  ✗ soffice/libreoffice 실행 파일 못 찾음")
        print("  설치: apt install libreoffice  /  brew install --cask libreoffice  /  Windows .msi")
    else:
        print(f"  soffice: {soffice}")
        t_a, pdf = extract_with_libreoffice(local)
        if t_a is None:
            print("  ✗ 변환 또는 텍스트 추출 실패")
        else:
            print(f"  ✓ {len(t_a)}자 추출")
            print(f"  PDF: {pdf}")
            print(f"  preview: {t_a[:300].strip()}…")

    print("\n=== 비교 결론 ===")
    print("  - 텍스트 신뢰도 (눈으로 비교): preview 깨짐·누락 없는 쪽 채택")
    print("  - 표 구조 보존: (a)만 가능. PDF에서 pdfplumber.tables() 별도 실행")
    print("  - 자동화: (b) hwp5txt가 가벼움 (의존성 1개) — 게시판 첨부 다수 처리에 권장")
    print("  - 학칙(1.3) 같은 1회성 중요 문서는 (a) + 수동 검증 권장")


# --------------------------------------------------------------------------- #
# crawl — Chunk 객체로 변환
# --------------------------------------------------------------------------- #

def crawl_hwp(
    source: str,
    *,
    domains: list[int],
    categories: Optional[list[str]] = None,
    source_title: Optional[str] = None,
    posted_at: Optional[str] = None,
    prefer: str = "hwp5txt",
    save_dir: str = "data/sprint1/hwp",
    client: Optional[HttpClient] = None,
) -> list[Chunk]:
    """HWP → Chunk 리스트 (1개. 매우 긴 경우 §2단계 chunking은 Phase C에서)."""
    local = (
        download_hwp(source, save_dir=save_dir, client=client)
        if _is_url(source) else source
    )
    res = extract_hwp(local, prefer=prefer)
    if not res.text:
        print(f"[skip] HWP 추출 실패: {local}", file=sys.stderr)
        return []

    title = source_title or os.path.splitext(os.path.basename(local))[0]
    source_url = source if _is_url(source) else f"file://{os.path.abspath(local)}"
    notes = f"hwp_method={res.method}"
    return [
        Chunk(
            text=res.text,
            source_type="T3",  # HWP를 T3로 분류 (PDF와 동급의 문서)
            source_url=source_url,
            source_title=title,
            domains=domains,
            categories=categories or [],
            freshness="dated" if posted_at else "static",
            posted_at=posted_at,
            section_path="hwp_body",
            notes=notes,
        )
    ]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description="HWP Pipeline (a + b 양쪽)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_s = sub.add_parser("spike", help="(a)·(b) 양쪽 결과 비교")
    p_s.add_argument("source", help="HWP URL 또는 로컬 경로")

    p_i = sub.add_parser("inspect", help="텍스트 추출 + 길이 진단")
    p_i.add_argument("source")
    p_i.add_argument("--prefer", default="hwp5txt", choices=["hwp5txt", "libreoffice", "auto"])

    p_c = sub.add_parser("crawl", help="텍스트 청크 → JSON Lines")
    p_c.add_argument("source")
    p_c.add_argument("--domains", required=True, help="콤마 구분 도메인 (예: 1 또는 1,8)")
    p_c.add_argument("--categories", default="")
    p_c.add_argument("--title", default=None)
    p_c.add_argument("--posted-at", default=None)
    p_c.add_argument("--prefer", default="hwp5txt", choices=["hwp5txt", "libreoffice", "auto"])
    p_c.add_argument("--out", default="data/sprint1/hwp_chunks.jsonl")
    p_c.add_argument("--save-dir", default="data/sprint1/hwp")

    args = p.parse_args()
    client = HttpClient()

    if args.mode == "spike":
        spike(args.source, client=client)
        return 0

    if args.mode == "inspect":
        local = download_hwp(args.source, client=client) if _is_url(args.source) else args.source
        res = extract_hwp(local, prefer=args.prefer)
        print(f"local : {local}")
        print(f"method: {res.method}")
        print(f"length: {len(res.text) if res.text else 0}자")
        if res.text:
            print(f"preview: {res.text[:600]}")
        return 0

    if args.mode == "crawl":
        domains = [int(d) for d in args.domains.split(",") if d.strip()]
        categories = [c for c in args.categories.split(",") if c.strip()]
        chunks = crawl_hwp(
            args.source,
            domains=domains,
            categories=categories,
            source_title=args.title,
            posted_at=getattr(args, "posted_at"),
            prefer=args.prefer,
            save_dir=args.save_dir,
            client=client,
        )
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        n = write_jsonl(chunks, args.out)
        total = sum(c.char_count for c in chunks)
        print(f"OK: {n} chunks → {args.out}")
        print(f"total_chars = {total}")
        for c in chunks[:1]:
            print(f"--- notes={c.notes} ({c.char_count}자)")
            print(c.text[:300])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
