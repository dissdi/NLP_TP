"""Termproject Task 2 entry point — chat UI + batch mode.

PDF 요구사항:
  · 웹 기반 인터페이스
  · 기능: 질문 입력, 응답 출력, **대화 흐름 표시**
  ⇒ gr.Chatbot 기반 멀티턴 표시. 질문 추천 chip, 환영 메시지, 출처 표시.

Two modes:
  (1) Interactive Chat UI       — `python -m chatbot_ui` (default)
  (2) Batch                     — `python -m chatbot_ui --batch \\
                                       --input data/test_chat.json \\
                                       --output outputs/chat_output.json`

Output schema (chat_output.json):
  [{"id": "q001", "question": "...", "answer": "...",
    "predicted_category": 0, "predicted_category_name": "졸업요건",
    "sources": [...], "used_fallback": false}]
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
EXAMPLES_PATH = os.path.join(ROOT, "src", "crawler", "phase_f", "examples.txt")

WELCOME = (
    "안녕하세요! **충남대학교 학내 정보 RAG 챗봇**입니다. 🎓\n\n"
    "다음 영역의 질문에 답할 수 있어요:\n"
    "- 📜 **졸업요건** (졸업학점, 전공·교양 요건)\n"
    "- 📢 **학교 공지사항** (백마광장·학사공지)\n"
    "- 📅 **학사일정** (수강신청·정정·시험·방학 일정)\n"
    "- 🍽 **식단** (학생식당·기숙사 식당 메뉴)\n"
    "- 🚌 **통학·셔틀버스** (시간표·노선·운휴 안내)\n\n"
    "_검색된 출처 context만 사용해 답변하며, 모르면 거절합니다._"
)


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
                text = x.get("question") or x.get("text") or x.get("query") or ""
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


def run_batch(input_path: str, output_path: str, minimal: bool = False) -> None:
    pipe = get_pipeline()
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = _normalize_batch_input(raw)
    print(f"[chatbot_ui] batch {len(items)} items from {input_path}", flush=True)

    results = []
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
        if minimal:
            results.append({"id": it["id"], "answer": ans})
        else:
            results.append({
                "id": it["id"],
                "question": q,
                "answer": ans,
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


# ────────────────────────────────────────────────────────────────────────
# Interactive UI (gr.Chatbot — 대화 흐름)
# ────────────────────────────────────────────────────────────────────────
def _load_examples() -> list[str]:
    if not os.path.exists(EXAMPLES_PATH):
        # Fallback examples covering the 5 categories
        return [
            "졸업학점은 몇 학점인가요?",
            "오늘 학생식당 점심 메뉴 알려줘",
            "2학기 수강신청 언제 시작해?",
            "셔틀버스 시간표 어떻게 되나요?",
            "이번 주 새로 올라온 공지 뭐 있어?",
        ]
    with open(EXAMPLES_PATH, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()][:8]


def _format_assistant_msg(ans: str, cat_name: str, conf: float,
                          sources: list[dict], fb: bool, tool: str,
                          elapsed: float) -> str:
    """Compose markdown for one assistant turn — answer + meta footer + sources."""
    badge = "🛑 정보 부족" if fb else "✅"
    cat_badge = f"  ·  📂 {cat_name} ({conf:.2f})" if cat_name else ""
    tool_badge = f"  ·  🛠 {tool}" if tool else ""
    foot = f"\n\n---\n_{badge}{cat_badge}{tool_badge}  ·  {elapsed:.1f}s_"

    src_md = ""
    if sources:
        lines = ["\n\n**출처**"]
        for i, s in enumerate(sources[:5], 1):
            title = (s.get("title", "") or "")[:90]
            url = s.get("source_url", "") or ""
            sc = float(s.get("rerank_score", 0.0))
            line = f"{i}. `{sc:+.2f}` {title}"
            if url:
                line += f"  <{url}>"
            lines.append(line)
        src_md = "\n".join(lines)

    return ans + src_md + foot


def _chat_turn(user_msg: str, history: list[list[str]]):
    """Append one turn to the history and return updated state.

    history format (Gradio messages mode): list of {role, content}.
    """
    if not user_msg or not user_msg.strip():
        return history, ""
    pipe = get_pipeline()
    t0 = time.time()
    try:
        r = pipe.answer(user_msg.strip())
        elapsed = time.time() - t0
        bot_text = _format_assistant_msg(
            ans=r.answer,
            cat_name=r.predicted_category_name or "",
            conf=float(r.classifier_confidence or 0.0),
            sources=[{"title": s.get("title", ""),
                      "source_url": s.get("source_url", ""),
                      "rerank_score": s.get("rerank_score", 0.0)}
                     for s in r.sources],
            fb=bool(r.used_fallback),
            tool=r.used_tool or "",
            elapsed=elapsed,
        )
    except Exception as e:  # pragma: no cover
        bot_text = f"[오류] {e}"
    history = list(history or [])
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": bot_text})
    return history, ""


def _chat_reset():
    """New conversation — return welcome turn."""
    return [{"role": "assistant", "content": WELCOME}], ""


def launch_ui(server_name: str = "0.0.0.0", server_port: int = 7860,
              share: bool = False) -> None:
    import gradio as gr

    # Pre-load pipeline so the first chat turn doesn't pay the cold-start.
    get_pipeline()

    with gr.Blocks(title="충남대 학내 정보 RAG 챗봇",
                   theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 충남대학교 학내 정보 RAG 챗봇")

        chatbot = gr.Chatbot(
            label="대화 흐름",
            value=[{"role": "assistant", "content": WELCOME}],
            type="messages",
            height=520,
            show_copy_button=True,
        )
        with gr.Row():
            user_box = gr.Textbox(
                label="",
                placeholder="질문을 입력하고 Enter (예: 졸업학점 몇 학점이야?)",
                lines=2,
                scale=7,
                autofocus=True,
            )
            with gr.Column(scale=1, min_width=80):
                submit_btn = gr.Button("전송", variant="primary")
                clear_btn = gr.Button("새 대화")

        gr.Examples(
            examples=_load_examples(),
            inputs=user_box,
            label="추천 질문",
            examples_per_page=8,
        )

        submit_btn.click(_chat_turn, [user_box, chatbot], [chatbot, user_box])
        user_box.submit(_chat_turn, [user_box, chatbot], [chatbot, user_box])
        clear_btn.click(_chat_reset, None, [chatbot, user_box])

    demo.launch(server_name=server_name, server_port=server_port, share=share)


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────
def parse_args():
    ap = argparse.ArgumentParser(description="Termproject chatbot (chat UI + batch)")
    ap.add_argument("--batch", action="store_true",
                    help="batch mode: read --input, write --output")
    ap.add_argument("--input", default=DEFAULT_BATCH_INPUT)
    ap.add_argument("--output", default=DEFAULT_BATCH_OUTPUT)
    ap.add_argument("--minimal", action="store_true",
                    help="batch output keeps only id+answer (per spec narrowing)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--share", action="store_true",
                    help="UI: gradio public share link")
    return ap.parse_args()


if __name__ == "__main__":
    a = parse_args()
    if a.batch:
        run_batch(a.input, a.output, minimal=a.minimal)
    else:
        launch_ui(server_name=a.host, server_port=a.port, share=a.share)
