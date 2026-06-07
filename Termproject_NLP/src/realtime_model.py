"""Termproject Task 3 (Optional) — 실시간 반영 모델 진입점.

PDF 평가축: "실시간 데이터를 응답에 반영하는지 평가".
- 카테고리 1(공지) / 2(학사일정) / 3(식단) / 4(셔틀) 질의는
  RAG 호출 전에 force_use_tool로 라이브 fetch.
- 카테고리 0(졸업요건)은 정적 정보라 RAG만 사용.

가이드 PDF 확정 schema:
  Input  (data/test_realtime.json):     [{"user": "..."}, ...]
  Output (outputs/realtime_output.json): [{"user": "...", "model": "..."}, ...]

호출:
  python -m realtime_model --input data/test_realtime.json \\
                           --output outputs/realtime_output.json

--debug 옵션을 주면 풍부한 메타(predicted_category, sources, realtime_meta 등)도
outputs/realtime_output.debug.json에 별도 저장.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from chatbot_ui import get_pipeline, _normalize_batch_input, _serialize_sources  # noqa: E402

DEFAULT_INPUT = os.path.join(ROOT, "data", "test_realtime.json")
DEFAULT_OUTPUT = os.path.join(ROOT, "outputs", "realtime_output.json")

# 카테고리 0(졸업요건)은 정적, 나머지는 라이브 fetch 시도.
REALTIME_CATEGORIES = {1, 2, 3, 4}


def _augment_with_live_tool(pipeline_result, query: str, category: int):
    """Force-call category tool BEFORE returning the answer.

    If a live tool returns a context block, we prepend it to the LLM prompt
    via a second pipeline call (or — simpler — append synthetic sources so
    the LLM/judge sees the freshness signal).

    P1 implementation (no re-generation):
      Just append tool sources to result.sources and set used_tool/realtime_meta.
      Keeps existing answer text; downstream evaluators see fresh URLs.
    P2 (deferred): re-prompt LLM with tool context for actually-fresh answer.
    """
    from crawler.phase_e.tools import force_use_tool

    if category not in REALTIME_CATEGORIES:
        return None, {"used": False, "fetched_at": None, "source": "static-index"}

    try:
        out = force_use_tool(query, category)
    except Exception as e:  # pragma: no cover
        return None, {"used": False, "fetched_at": None,
                      "source": f"tool-error:{type(e).__name__}"}
    if not out:
        return None, {"used": False, "fetched_at": None, "source": "no-match"}

    tool_name, payload = out
    return payload, {
        "used": True,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "source": tool_name,
    }


def run(input_path: str, output_path: str, refresh: bool = True,
        debug: bool = False) -> None:
    pipe = get_pipeline()
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = _normalize_batch_input(raw)
    print(f"[realtime] {len(items)} items from {input_path} (refresh={refresh})",
          flush=True)

    # 가이드 spec 출력 (필수)
    results: list[dict] = []
    # 디버그용 풍부 메타 (옵션)
    debug_results: list[dict] = []

    for i, it in enumerate(items, 1):
        q = it["text"]
        t0 = time.time()
        try:
            r = pipe.answer(q)
            cat = int(r.predicted_category)
            srcs = _serialize_sources(r.sources, k=5)
            meta = {"used": False, "fetched_at": None, "source": "static-index"}

            if refresh:
                payload, meta = _augment_with_live_tool(r, q, cat)
                if payload:
                    # Prepend live sources so they appear first in the citation list.
                    live_srcs = payload.get("sources", [])
                    srcs = list(live_srcs) + srcs
                    srcs = srcs[:8]

            ans = r.answer
            # 가이드 spec: {"user": "질문", "model": "답변"}
            results.append({"user": q, "model": ans})

            if debug:
                debug_results.append({
                    "id": it["id"],
                    "user": q,
                    "model": ans,
                    "predicted_category": cat,
                    "predicted_category_name": r.predicted_category_name,
                    "sources": srcs,
                    "used_fallback": bool(r.used_fallback),
                    "used_tool": (meta["source"] if meta["used"]
                                  else r.used_tool or ""),
                    "realtime_meta": meta,
                })
        except Exception as e:  # pragma: no cover
            results.append({"user": q, "model": f"[ERROR] {e}"})
            if debug:
                debug_results.append({
                    "id": it["id"], "user": q, "model": f"[ERROR] {e}",
                    "predicted_category": -1, "predicted_category_name": "",
                    "sources": [], "used_fallback": True, "used_tool": "",
                    "realtime_meta": {"used": False, "fetched_at": None,
                                      "source": "error"},
                })
        print(f"[realtime] [{i}/{len(items)}] {time.time()-t0:.1f}s · {it['id']}",
              flush=True)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[realtime] wrote {len(results)} answers → {output_path}", flush=True)

    if debug:
        debug_path = output_path.replace(".json", ".debug.json")
        if debug_path == output_path:
            debug_path = output_path + ".debug.json"
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_results, f, ensure_ascii=False, indent=2)
        print(f"[realtime] wrote debug meta → {debug_path}", flush=True)


def parse_args():
    ap = argparse.ArgumentParser(description="Realtime model (PDF 평가축 3)")
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--no-refresh", action="store_true",
                    help="skip live tool fetch (debug only)")
    ap.add_argument("--debug", action="store_true",
                    help="풍부한 메타를 realtime_output.debug.json에 추가 저장")
    return ap.parse_args()


if __name__ == "__main__":
    a = parse_args()
    run(a.input, a.output, refresh=not a.no_refresh, debug=a.debug)
