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

    get_pipeline()

    CUSTOM_CSS = """
    /* ------- Claude-style dark theme ------- */
    :root {
      --cn-bg: #1f1e1d;
      --cn-bg-2: #262524;
      --cn-bg-3: #2f2d2b;
      --cn-bg-4: #3a3835;
      --cn-border: #38353230;
      --cn-text: #ececec;
      --cn-text-dim: #9b958e;
      --cn-accent: #d97757;
      --cn-accent-hover: #c66643;
    }
    html, body { background: var(--cn-bg) !important; color: var(--cn-text) !important;
                 height: 100vh !important; overflow: hidden !important; margin: 0 !important; }
    .gradio-container { max-width: 100% !important; height: 100vh !important;
                         padding: 0 !important; background: var(--cn-bg) !important;
                         overflow: hidden !important; }
    .gradio-container *, body, html { font-family: -apple-system, BlinkMacSystemFont,
                                       "Pretendard", "Apple SD Gothic Neo", sans-serif; }
    .gradio-container > .main { height: 100vh !important; overflow: hidden !important; }
    footer, .footer { display: none !important; }

    /* Top row fills viewport */
    .gradio-container > .main > div { height: 100vh !important; overflow: hidden !important; }

    /* Sidebar */
    #sidebar { background: var(--cn-bg-2) !important; border-right: 1px solid #34322f !important;
               height: 100vh !important; padding: 14px 10px !important;
               display: flex !important; flex-direction: column !important; gap: 8px !important;
               box-sizing: border-box; overflow: hidden; }
    #sidebar > .gr-button, #sidebar button#new_chat_btn { width: 100% !important; }
    #new_chat_btn { background: transparent !important; color: var(--cn-text) !important;
                    border: 1px solid #4a4744 !important; border-radius: 14px !important;
                    padding: 11px 14px !important; font-size: 13.5px !important;
                    font-weight: 500 !important; cursor: pointer !important;
                    transition: background 0.15s ease; }
    #new_chat_btn:hover { background: var(--cn-bg-3) !important; }
    #sidebar .sidebar-title { font-weight: 500; font-size: 11.5px; color: var(--cn-text-dim);
                              padding: 14px 8px 4px; letter-spacing: 0.04em;
                              text-transform: uppercase; }
    #sidebar .session-list { flex: 1; overflow-y: auto; }
    #sidebar .session-list button { width: 100%; text-align: left; background: transparent;
                                     border: none; padding: 9px 10px; border-radius: 8px;
                                     color: var(--cn-text); font-size: 13.5px; cursor: default;
                                     margin-bottom: 2px; }
    #sidebar .session-list .active { background: var(--cn-bg-3); }
    #sidebar .session-list .disabled { color: var(--cn-text-dim); font-style: italic; font-size: 12.5px; }

    /* Main column */
    #main_col { background: var(--cn-bg) !important; height: 100vh !important;
                display: flex !important; flex-direction: column !important;
                padding: 0 !important; gap: 0 !important; overflow: hidden !important; }
    #main_area { width: 100%; max-width: 920px; margin: 0 auto;
                 padding: 22px 28px 12px; flex: 1; min-height: 0;
                 display: flex; flex-direction: column; overflow: hidden; }
    #main_area h3 { color: var(--cn-text); margin: 0 0 14px 0; font-weight: 600; }

    /* Chatbot */
    #chatbot { background: transparent !important; border: none !important;
               box-shadow: none !important; flex: 1 !important; min-height: 0 !important; }
    #chatbot > div { background: transparent !important; }
    /* Hide chatbot built-in toolbar/trash/scroll buttons */
    #chatbot button[aria-label="Clear"],
    #chatbot button[title="Clear"],
    #chatbot .toolbar,
    #chatbot .icon-button-wrapper:has(svg[aria-label*="Delete"]),
    #chatbot > div > button { display: none !important; }
    /* Message bubbles */
    #chatbot .message-wrap, #chatbot .message { background: transparent !important; }
    .bot-row .md, .user-row .md,
    #chatbot .bot, #chatbot .user,
    .message-content {
      background: var(--cn-bg-2) !important; color: var(--cn-text) !important;
      border: 1px solid #34322f !important; border-radius: 14px !important;
      padding: 12px 14px !important;
    }
    #chatbot .copy-button, #chatbot .icon-button { color: var(--cn-text-dim) !important; }

    /* Input area */
    #input_wrap { width: 100%; max-width: 920px; margin: 0 auto;
                  padding: 6px 28px 22px; box-sizing: border-box; flex-shrink: 0; }
    #input_area { gap: 10px !important; align-items: flex-end !important; }
    #user_box, #user_box > div, #user_box .gr-form { background: transparent !important;
                                                       border: none !important; box-shadow: none !important; }
    #user_box textarea { background: var(--cn-bg-2) !important; color: var(--cn-text) !important;
                          border: 1px solid #34322f !important;
                          border-radius: 16px !important; padding: 14px 18px !important;
                          font-size: 15px !important; line-height: 1.55 !important;
                          resize: none !important; overflow-y: hidden !important;
                          min-height: 84px !important; max-height: 200px !important;
                          box-shadow: 0 1px 2px rgba(0,0,0,0.15) !important;
                          transition: border-color 0.15s ease; }
    #user_box textarea:focus { border-color: var(--cn-accent) !important; outline: none !important; }
    #user_box textarea::placeholder { color: var(--cn-text-dim) !important; }
    #submit_btn { background: var(--cn-accent) !important; color: white !important;
                  border: none !important; border-radius: 14px !important;
                  height: 84px !important; min-width: 88px !important;
                  font-weight: 600 !important; font-size: 14px !important;
                  cursor: pointer !important; transition: background 0.15s ease;
                  box-shadow: 0 1px 2px rgba(0,0,0,0.15) !important; }
    #submit_btn:hover { background: var(--cn-accent-hover) !important; }

    /* Force chatbot to fill remaining height */
    #chatbot { height: 100% !important; min-height: 0 !important; }
    #chatbot > div { height: 100% !important; }
    #chatbot .bubble-wrap { height: 100% !important; padding: 8px 0 !important; }

    /* Kill ALL toolbar chrome on chatbot (trash, scroll-down arrow, etc) */
    #chatbot button.icon-button,
    #chatbot .icon-button-wrapper,
    #chatbot button[aria-label*="Clear"],
    #chatbot button[aria-label*="trash"],
    #chatbot button[aria-label*="Delete"],
    #chatbot button[aria-label*="Scroll"],
    #chatbot .scroll-hide,
    #chatbot > button,
    #chatbot > div > button { display: none !important; }

    /* Flatten nested message containers — single bubble per message */
    #chatbot .message,
    #chatbot .message-row,
    #chatbot .message-wrap,
    #chatbot .bot-row,
    #chatbot .user-row { background: transparent !important; border: none !important;
                         box-shadow: none !important; padding: 6px 0 !important; }
    #chatbot .message > div,
    #chatbot .message-content { background: var(--cn-bg-2) !important;
                                 border: 1px solid #34322f !important;
                                 border-radius: 14px !important;
                                 padding: 12px 14px !important;
                                 color: var(--cn-text) !important; }
    #chatbot .message > div > div,
    #chatbot .message-content > div { background: transparent !important;
                                       border: none !important; padding: 0 !important; }
    """

    with gr.Blocks(title="충남대 학내 정보 RAG 챗봇",
                   theme=gr.themes.Soft(),
                   css=CUSTOM_CSS) as demo:
        with gr.Row(equal_height=False):
            # Sidebar — 새 채팅 (top) + 대화 리스트
            with gr.Column(scale=1, min_width=240, elem_id="sidebar"):
                clear_btn = gr.Button("＋ 새 채팅", elem_id="new_chat_btn", variant="secondary")
                gr.HTML('<div class="sidebar-title">대화</div>')
                gr.HTML(
                    '<div class="session-list">'
                    '<button class="active">현재 대화</button>'
                    '<button class="disabled">(이전 대화 없음)</button>'
                    '</div>'
                )

            # Main column
            with gr.Column(scale=5, elem_id="main_col"):
                with gr.Column(elem_id="main_area"):
                    gr.Markdown("### 충남대학교 학내 정보 RAG 챗봇")
                    chatbot = gr.Chatbot(
                        label="",
                        value=[{"role": "assistant", "content": WELCOME}],
                        type="messages",
                        show_copy_button=True,
                        elem_id="chatbot",
                        show_label=False,
                        show_share_button=False,
                        bubble_full_width=False,
                    )
                with gr.Column(elem_id="input_wrap"):
                    with gr.Row(elem_id="input_area"):
                        user_box = gr.Textbox(
                            label="",
                            placeholder="질문을 입력하고 Enter (Shift+Enter = 줄바꿈)",
                            lines=3,
                            max_lines=10,
                            scale=10,
                            autofocus=True,
                            elem_id="user_box",
                            show_label=False,
                            container=False,
                        )
                        submit_btn = gr.Button("전송", variant="primary",
                                               scale=1, min_width=84, elem_id="submit_btn")

        submit_btn.click(_chat_turn, [user_box, chatbot], [chatbot, user_box])
        user_box.submit(_chat_turn, [user_box, chatbot], [chatbot, user_box])
        clear_btn.click(_chat_reset, None, [chatbot, user_box])

        # Enter = submit, Shift+Enter = newline + auto-resize textarea (no scrollbar)
        demo.load(
            None, None, None,
            js="""
            () => {
              const wait = setInterval(() => {
                const ta = document.querySelector('#user_box textarea');
                const btn = document.querySelector('#submit_btn');
                if (!ta || !btn) return;
                clearInterval(wait);
                const autoResize = () => {
                  ta.style.height = 'auto';
                  ta.style.height = Math.min(ta.scrollHeight, 220) + 'px';
                };
                ta.addEventListener('input', autoResize);
                ta.addEventListener('keydown', (e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                    e.preventDefault();
                    btn.click();
                    setTimeout(autoResize, 0);
                  }
                });
                autoResize();
              }, 200);
            }
            """,
        )

    demo.launch(server_name=server_name, server_port=server_port, share=share)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Termproject chatbot (chat UI + batch)")
    ap.add_argument("--batch", action="store_true", help="batch mode")
    ap.add_argument("--input", default=DEFAULT_BATCH_INPUT)
    ap.add_argument("--output", default=DEFAULT_BATCH_OUTPUT)
    ap.add_argument("--minimal", action="store_true", help="batch: only {id, answer}")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--share", action="store_true")
    return ap.parse_args()


if __name__ == "__main__":
    a = parse_args()
    if a.batch:
        run_batch(a.input, a.output, minimal=a.minimal)
    else:
        launch_ui(server_name=a.host, server_port=a.port, share=a.share)
