"""Phase F - Gradio web app wrapping the RAG pipeline.

Run:
  CUDA_VISIBLE_DEVICES=9 python -m crawler.phase_f.app
  # then open the printed local URL (http://0.0.0.0:7860) or use share=True
"""
from __future__ import annotations

import os
import time

import gradio as gr

from crawler.phase_e.pipeline import RAGPipeline

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples.txt")

# Singleton pipeline loaded once at module import (heavy: bge-m3 + reranker + 14B LLM).
print("[app] loading RAG pipeline ... (this can take a minute)", flush=True)
_t0 = time.time()
PIPELINE = RAGPipeline()
print(f"[app] retriever+reranker loaded in {time.time()-_t0:.1f}s", flush=True)

# Warmup: force LLM (Qwen 14B 4-bit) into GPU NOW so the first user query
# does not incur a 30~60s cold-start. Memory stabilizes here.
print("[app] warming up LLM ...", flush=True)
_t1 = time.time()
from crawler.phase_e.llm import chat as _chat
_ = _chat(user_msg="ping", max_new_tokens=4)
print(f"[app] LLM warmed up in {time.time()-_t1:.1f}s — ready", flush=True)


def _load_examples() -> list[str]:
    if not os.path.exists(EXAMPLES_PATH):
        return []
    with open(EXAMPLES_PATH, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f.readlines() if ln.strip()]


def _format_sources(sources: list[dict], k: int = 5) -> str:
    if not sources:
        return "_(no sources)_"
    lines = []
    for i, s in enumerate(sources[:k], 1):
        title = s.get("title", "")[:90]
        url = s.get("source_url", "")
        score = s.get("rerank_score", 0.0)
        line = f"**{i}.** `rerank={score:+.3f}` · {title}"
        if url:
            line += f"\n   <{url}>"
        lines.append(line)
    return "\n\n".join(lines)


def answer_fn(query: str):
    if not query or not query.strip():
        return "질문을 입력하세요.", "", "", ""
    t0 = time.time()
    res = PIPELINE.answer(query.strip())
    elapsed = time.time() - t0
    answer = res.answer
    fb_badge = "🛑 FALLBACK (참고자료 부족)" if res.used_fallback else "✅ 답변 완료"
    meta = (
        f"{fb_badge}  ·  top rerank score: {res.top_rerank_score:+.3f}  ·  "
        f"sources: {len(res.sources)}  ·  elapsed: {elapsed:.1f}s"
    )
    sources_md = _format_sources(res.sources, k=5)
    return answer, meta, sources_md, ""


with gr.Blocks(title="충남대 학내 정보 RAG 챗봇") as demo:
    gr.Markdown(
        "# 충남대학교 학내 정보 RAG 챗봇\n"
        "학칙·공지·학과·기숙사·도서관 등 학내 공개 정보 기반 질의 응답.\n"
        "_(retrieved context만 사용. 모르면 거절합니다.)_"
    )
    with gr.Row():
        with gr.Column(scale=3):
            query_box = gr.Textbox(
                label="질문",
                placeholder="예: 졸업요건 학점은 몇 학점인가요?",
                lines=2,
            )
            submit_btn = gr.Button("질문하기", variant="primary")
            gr.Examples(examples=_load_examples(), inputs=query_box, label="예시 질문")
        with gr.Column(scale=4):
            meta_box = gr.Markdown(label="상태")
            answer_box = gr.Textbox(
                label="답변",
                lines=10,
                interactive=False,
            )
            with gr.Accordion("출처 (top-5)", open=True):
                sources_box = gr.Markdown()
    err_box = gr.Markdown(visible=False)
    submit_btn.click(
        fn=answer_fn,
        inputs=[query_box],
        outputs=[answer_box, meta_box, sources_box, err_box],
    )
    query_box.submit(
        fn=answer_fn,
        inputs=[query_box],
        outputs=[answer_box, meta_box, sources_box, err_box],
    )


if __name__ == "__main__":
    import sys
    share = "--share" in sys.argv
    demo.launch(server_name="0.0.0.0", server_port=7860, share=share)
