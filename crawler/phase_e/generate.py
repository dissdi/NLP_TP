"""Answer generation. Korean strings in prompts/*.txt."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from .llm import DEFAULT_4BIT, DEFAULT_LLM, chat

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
RERANK_FALLBACK_THRESHOLD = 0.15

# --- Truncation handling -----------------------------------------------------
# When the LLM hits max_new_tokens without emitting EOS, the answer is cut mid-
# sentence. We detect this (EOS missing OR final token isn't a sentence-ender),
# trim to the last complete sentence, and append a notice pointing users to
# the sources panel for the omitted detail.

TRUNCATION_NOTICE = " (자세한 사항은 위 출처를 참고하세요.)"
# Match Korean and ASCII sentence terminators; require non-letter after to
# avoid false hits inside numbers like "1.75".
_SENT_END_RE = re.compile(r"(다\.|요\.|니다\.|습니다\.|까\?|[.?!])(?=\s|$|[\"')\]])")
_TAIL_TERMINATORS = (
    "다.", "요.", "니다.", "습니다.", "까?", ".", "?", "!",
    ".)", ".\"", "요.)", "다.)",
)


def _looks_finished(text: str) -> bool:
    return text.rstrip().endswith(_TAIL_TERMINATORS)


def _truncate_at_last_sentence(text: str) -> str:
    """Return text trimmed to the last complete sentence terminator.

    If no terminator is found, returns the stripped original (the notice
    still gets appended by the caller so the user knows it was incomplete).
    """
    matches = list(_SENT_END_RE.finditer(text))
    if not matches:
        return text.rstrip()
    return text[: matches[-1].end()].rstrip()


def _apply_truncation_notice(text: str, eos_reached: bool) -> str:
    """Trim + append notice if the answer appears truncated.

    Truncated = (EOS not emitted) OR (EOS emitted but tail is not a terminator).
    """
    if eos_reached and _looks_finished(text):
        return text
    trimmed = _truncate_at_last_sentence(text)
    if TRUNCATION_NOTICE.strip() in trimmed:
        return trimmed
    return trimmed + TRUNCATION_NOTICE


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
        return GenerationResult(answer=FALLBACK_MSG, used_fallback=True, top_rerank_score=top_score, sources=sources)
    context = _format_context(reranked, max_chunks=max_chunks)
    user_msg = _USER_TEMPLATE.format(query=query, context=context)
    answer, eos_reached = chat(
        user_msg=user_msg,
        system_msg=_ANSWER_SYS,
        model_id=model_id,
        load_in_4bit=load_in_4bit,
        max_new_tokens=max_new_tokens,
        temperature=0.0,
        return_meta=True,
    )
    answer = _apply_truncation_notice(answer.strip(), eos_reached)
    return GenerationResult(answer=answer, used_fallback=False, top_rerank_score=top_score, sources=sources)
