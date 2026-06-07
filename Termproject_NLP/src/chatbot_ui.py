"""Termproject batch evaluator (구. gradio chat UI).

UI는 FastAPI + 정적 HTML/JS(`app.py`)로 옮겨갔다. 본 파일은
`bash chatbot.sh --batch` 진입점만 유지한다.

가이드 PDF 확정 schema:
  Input  (data/test_chat.json):     [{"user": "..."}, ...]
  Output (outputs/chat_output.json): [{"user": "...", "model": "..."}, ...]

--debug 옵션을 주면 풍부한 메타(predicted_category, sources 등)도
outputs/chat_output.debug.json에 별도 저장한다. 기본 output은 가이드 spec 준수.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from crawler.phase_e.pipeline import RAGPipeline  # noqa: E402


DEFAULT_BATCH_INPUT = os.path.join(ROOT, "data", "test_chat.json")
DEFAULT_BATCH_OUTPUT = os.path.join(ROOT, "outputs", "chat_output.json")


# ────────────────────────────────────────────────────────────────────────
# Singleton pipeline
# ────────────────────────────────────────────────────────────────────────
_PIPELINE: RAGPipeline | None = None


def get_pipeline() -> RAGPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        print("[chatbot_ui] loading RAG pipeline (retriever + reranker)…", flush=True)
        t0 = time.time()
        _PIPELINE = RAGPipeline()
        print(f"[chatbot_ui] retriever+reranker ready in {time.time()-t0:.1f}s",
              flush=True)
        try:
            from crawler.phase_e.llm import chat as _chat
            print("[chatbot_ui] warming up LLM…", flush=True)
            t1 = time.time()
            _ = _chat(user_msg="ping", max_new_tokens=4)
            print(f"[chatbot_ui] LLM warmed up in {time.time()-t1:.1f}s", flush=True)
        except Exception as e:  # pragma: no cover
            print(f"[chatbot_ui] LLM warmup skipped: {e}", flush=True)
    return _PIPELINE


# ────────────────────────────────────────────────────────────────────────
# Batch mode
# ────────────────────────────────────────────────────────────────────────
def _normalize_batch_input(raw: Any) -> list[dict]:
    items: list[dict] = []
    if isinstance(raw, list):
        for i, x in enumerate(raw):
            if isinstance(x, dict):
                qid = x.get("id") or x.get("qa_id") or x.get("qid") or f"q{i:05d}"
                # 가이드 spec은 "user" 키. 호환성 위해 question/text/query도 인식.
                text = (
                    x.get("user")
                    or x.get("question")
                    or x.get("text")
                    or x.get("query")
                    or ""
                )
            elif isinstance(x, str):
                qid, text = f"q{i:05d}", x
            else:
                continue
            items.append({"id": str(qid), "text": text})
    elif isinstance(raw, dict):
        if "items" in raw and isinstance(raw["items"], list):
            return _normalize_batch_input(raw["items"])
        for k, v in raw.items():
            items.append({"id": str(k), "text": v if isinstance(v, str) else ""})
    return items


def _serialize_sources(sources: list[dict], k: int = 5) -> list[dict]:
    out = []
    for s in sources[:k]:
        out.append({
            "chunk_id": s.get("chunk_id", ""),
            "title": s.get("title", "")[:200],
            "source_url": s.get("source_url", ""),
            "rerank_score": float(s.get("rerank_score", 0.0)),
        })
    return out


def run_batch(input_path: str, output_path: str, debug: bool = False) -> None:
    pipe = get_pipeline()
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = _normalize_batch_input(raw)
    print(f"[chatbot_ui] batch {len(items)} items from {input_path}", flush=True)

    # 가이드 spec 출력 (필수)
    results: list[dict] = []
    # 디버그용 풍부 메타 (옵션)
    debug_results: list[dict] = []

    for i, it in enumerate(items, 1):
        q = it["text"]
        t0 = time.time()
        try:
            r = pipe.answer(q)
            ans = r.answer
            cat = int(r.predicted_category)
            cat_name = r.predicted_category_name
            conf = float(r.classifier_confidence)
            srcs = _serialize_sources(r.sources, k=5)
            fb = bool(r.used_fallback)
            tool = r.used_tool or ""
        except Exception as e:
            ans = f"[ERROR] {e}"
            cat, cat_name, conf = -1, "", 0.0
            srcs, fb, tool = [], True, ""
        elapsed = time.time() - t0
        print(f"[chatbot_ui] [{i}/{len(items)}] {elapsed:.1f}s · {it['id']}",
              flush=True)

        # 가이드 spec: {"user": "질문", "model": "답변"}
        results.append({"user": q, "model": ans})

        if debug:
            debug_results.append({
                "id": it["id"],
                "user": q,
                "model": ans,
                "predicted_category": cat,
                "predicted_category_name": cat_name,
                "classifier_confidence": conf,
                "sources": srcs,
                "used_fallback": fb,
                "used_tool": tool,
            })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[chatbot_ui] wrote {len(results)} answers → {output_path}", flush=True)

    if debug:
        debug_path = output_path.replace(".json", ".debug.json")
        if debug_path == output_path:
            debug_path = output_path + ".debug.json"
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_results, f, ensure_ascii=False, indent=2)
        print(f"[chatbot_ui] wrote debug meta → {debug_path}", flush=True)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(
        description="Termproject batch evaluator (use `bash chatbot.sh ui` for the web UI)"
    )
    ap.add_argument("--batch", action="store_true",
                    help="batch mode (required — UI는 app.py로 이동)")
    ap.add_argument("--input", default=DEFAULT_BATCH_INPUT)
    ap.add_argument("--output", default=DEFAULT_BATCH_OUTPUT)
    ap.add_argument("--debug", action="store_true",
                    help="batch: 풍부한 메타(predicted_category, sources 등)를 chat_output.debug.json에 추가 저장")
    return ap.parse_args()


if __name__ == "__main__":
    a = parse_args()
    if not a.batch:
        print(
            "[chatbot_ui] UI는 FastAPI 서버(app.py)로 이동했습니다.\n"
            "             웹 UI: bash chatbot.sh ui   (또는 uvicorn app:app --port 7860)\n"
            "             배치 : bash chatbot.sh --batch",
            file=sys.stderr,
        )
        sys.exit(2)
    run_batch(a.input, a.output, debug=a.debug)
