"""Answer generation from retrieved + reranked chunks.

Prompts are kept in crawler/phase_e/prompts/*.txt to avoid multi-byte
truncation issues we hit with long Korean strings inside .py files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .llm import DEFAULT_4BIT, DEFAULT_LLM, chat

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
RERANK_FALLBACK_THRESHOLD = 0.3


def _load_prompt(name: str) -> str:
    path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


_ANSWER_SYS = _load_prompt("answer_v2")


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
    FALLBACK_MSG = "관련 정보를 찾지 못했습니다. 학사 담당 부서에 문의 바랍니다."

    if not reranked:
        return GenerationResult(
            answer=FALLBACK_MSG,
            used_fallback=True,
            top_rerank_score=0.0,
            sources=[],
        )

    top_score = float((reranked[0].meta or {}).get("_rerank_score", 0.0))
    sources: list[dict] = []
    for c in reranked[:max_chunks]:
        m = c.meta or {}
        sources.append({
            "chunk_id": c.chunk_id,
            "title": (m.get("source_title") or "").strip(),
            "source_url": (m.get("_canonical_url") or m.get("source_url") or "").strip(),
            "rerank_score": float(m.get("_rerank_score", 0.0)),
        })

    if top_score < fallback_threshold:
        return GenerationResult(
            answer=FALLBACK_MSG,
            used_fallback=True,
            top_rerank_score=top_score,
            sources=sources,
        )

    context = _format_context(reranked, max_chunks=max_chunks)
    user_msg = f"[질문]\n{query}\n\n[참고자료]\n{context}"
    answer = chat(
        user_msg=user_msg,
        system_msg=_ANSWER_SYS,
        model_id=model_id,
        load_in_4bit=load_in_4bit,
        max_new_tokens=max_new_tokens,
        temperature=0.0,
    )
    return GenerationResult(
        answer=answer.strip(),
        used_fallback=False,
        top_rerank_score=top_score,
        sources=sources,
    )
