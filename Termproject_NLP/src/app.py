"""FastAPI server — Claude-style chat UI in front of RAGPipeline.

진입점:
  uvicorn app:app --host 0.0.0.0 --port 7860

엔드포인트:
  GET  /              → static/index.html
  GET  /api/health    → {ok, ready}
  POST /api/chat      → {message} → {answer, sources, category, confidence, fallback, tool, elapsed}
  POST /api/reset     → 새 대화 (서버 측 상태 없음 — 클라이언트가 history 관리)

백엔드는 chatbot_ui.py와 동일한 RAGPipeline 싱글톤을 공유한다.
"""

import os
import sys
import time
from typing import Any, List, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATIC_DIR = os.path.join(HERE, "static")
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from crawler.phase_e.pipeline import RAGPipeline  # noqa: E402


# ────────────────────────────────────────────────────────────────────────
# Singleton pipeline (지연 로드 — uvicorn 부팅 시점에 LLM 로딩 30s+ 차지)
# ────────────────────────────────────────────────────────────────────────
_PIPELINE: Optional[RAGPipeline] = None
_LOAD_ERR: Optional[str] = None


def get_pipeline() -> RAGPipeline:
    global _PIPELINE, _LOAD_ERR
    if _PIPELINE is None:
        print("[app] loading RAG pipeline (retriever + reranker)…", flush=True)
        t0 = time.time()
        try:
            _PIPELINE = RAGPipeline()
            print(f"[app] retriever+reranker ready in {time.time()-t0:.1f}s",
                  flush=True)
            try:
                from crawler.phase_e.llm import chat as _chat
                print("[app] warming up LLM…", flush=True)
                t1 = time.time()
                _ = _chat(user_msg="ping", max_new_tokens=4)
                print(f"[app] LLM warmed up in {time.time()-t1:.1f}s", flush=True)
            except Exception as e:
                print(f"[app] LLM warmup skipped: {e}", flush=True)
        except Exception as e:
            _LOAD_ERR = str(e)
            print(f"[app] pipeline load FAILED: {e}", flush=True)
            raise
    return _PIPELINE


# ────────────────────────────────────────────────────────────────────────
# App
# ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="충남대 학내 정보 RAG 챗봇", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    # eagerly load so first request isn't slow; failure logged but server still serves /
    try:
        get_pipeline()
    except Exception:
        pass


# ----- API models -----
class ChatRequest(BaseModel):
    message: str


class SourceOut(BaseModel):
    title: str = ""
    source_url: str = ""
    rerank_score: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceOut] = []
    category: str = ""
    category_id: int = -1
    confidence: float = 0.0
    fallback: bool = False
    tool: str = ""
    elapsed: float = 0.0


# ----- routes -----
@app.get("/api/health")
def health() -> "dict[str, Any]":
    return {
        "ok": True,
        "ready": _PIPELINE is not None,
        "error": _LOAD_ERR,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> ChatResponse:
    q = (req.message or "").strip()
    if not q:
        return ChatResponse(answer="", sources=[])
    t0 = time.time()
    try:
        pipe = get_pipeline()
        r = pipe.answer(q)
        elapsed = time.time() - t0
        srcs = [
            SourceOut(
                title=(s.get("title", "") or "")[:200],
                source_url=s.get("source_url", "") or "",
                rerank_score=float(s.get("rerank_score", 0.0)),
            )
            for s in (r.sources or [])[:5]
        ]
        return ChatResponse(
            answer=r.answer,
            sources=srcs,
            category=r.predicted_category_name or "",
            category_id=int(r.predicted_category),
            confidence=float(r.classifier_confidence or 0.0),
            fallback=bool(r.used_fallback),
            tool=r.used_tool or "",
            elapsed=elapsed,
        )
    except Exception as e:
        return ChatResponse(
            answer=f"[오류] {e}",
            sources=[],
            fallback=True,
            elapsed=time.time() - t0,
        )


@app.post("/api/reset")
def reset_endpoint() -> "dict[str, bool]":
    # 서버는 상태 없음. 클라이언트가 history 비우면 끝.
    return {"ok": True}


# ----- static -----
# Mount /static/* explicitly so / can serve index.html separately.
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> Any:
    idx = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(idx):
        return FileResponse(idx)
    return JSONResponse(
        {"error": "static/index.html missing", "static_dir": STATIC_DIR},
        status_code=500,
    )


if __name__ == "__main__":  # pragma: no cover — convenience entry
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=False)