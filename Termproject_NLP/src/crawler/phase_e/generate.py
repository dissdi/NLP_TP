"""Answer generation. Korean strings in prompts/*.txt."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .llm import DEFAULT_4BIT, DEFAULT_LLM, chat

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
RERANK_FALLBACK_THRESHOLD = 0.15


def _load_prompt(name: str) -> str:
    with open(os.path.join(_PROMPTS_DIR, f"{name}.txt"), "r", encoding="utf-8") as f:
        return f.read().strip()


_ANSWER_SYS = _load_prompt("answer_v2")
FALLBACK_MSG = _load_prompt("fallback_msg")
_USER_TEMPLATE = _load_prompt("user_msg_template")


@dataclass
class GenerationResult:
    answer: str
    used_fallback: bool
    top_rerank_score: float
    sources: list[dict]


def _format_context(chunks: list, max_chunks: int = 8) -> str:
    lines: list[str] = []
    for i, c in enumerate(chunks[:max_chunks], 1):
        m = c.meta or {}
        title = (m.get("source_title") or "").strip()
        body = (m.get("text") or m.get("_passage") or "").strip()
        if not body:
            continue
        lines.append(f"[{i}] title: {title}")
        lines.append(body)
        lines.append("")
    return "\n".join(lines).rstrip()


def generate_answer(
    query: str,
    reranked: list,
    fallback_threshold: float = RERANK_FALLBACK_THRESHOLD,
    max_chunks: int = 8,
    max_new_tokens: int = 512,
    model_id: str = DEFAULT_LLM,
    load_in_4bit: bool = DEFAULT_4BIT,
) -> GenerationResult:
    if not reranked:
        return GenerationResult(answer=FALLBACK_MSG, used_fallback=True, top_rerank_score=0.0, sources=[])
    top_score = float((reranked[0].meta or {}).get("_rerank_score", 0.0))
    # dept_rescue가 promote한 chunk는 도메인 매칭이라는 deterministic 신호.
    # cross-encoder가 점수를 낮게 줘도(예: 기계 me.cnu.ac.kr 0.13) fallback 우회.
    dept_rescued = bool((reranked[0].meta or {}).get("_dept_rescued"))
    sources: list[dict] = []
    for c in reranked[:max_chunks]:
        m = c.meta or {}
        sources.append({
            "chunk_id": c.chunk_id,
            "title": (m.get("source_title") or "").strip(),
            "source_url": (m.get("_canonical_url") or m.get("source_url") or "").strip(),
            "rerank_score": float(m.get("_rerank_score", 0.0)),
        })
    if top_score < fallback_threshold and not dept_rescued:
        return GenerationResult(answer=FALLBACK_MSG, used_fallback=True, top_rerank_score=top_score, sources=sources)
    context = _format_context(reranked, max_chunks=max_chunks)
    user_msg = _USER_TEMPLATE.format(query=query, context=context)
    answer = chat(
        user_msg=user_msg,
        system_msg=_ANSWER_SYS,
        model_id=model_id,
        load_in_4bit=load_in_4bit,
        max_new_tokens=max_new_tokens,
        temperature=0.0,
    )
    return GenerationResult(answer=answer.strip(), used_fallback=False, top_rerank_score=top_score, sources=sources)
