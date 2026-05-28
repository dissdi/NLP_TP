"""Answer generation from retrieved + reranked chunks.

Policy (project-nlp-tp-design-principles):
  - Accuracy >> naturalness >> style
  - Use ONLY retrieved context, no prior knowledge
  - If rerank score below threshold -> "정보 없음" fallback (no hallucination)
  - Answer template: facts -> sources (chunk title / source_url)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .llm import DEFAULT_4BIT, DEFAULT_LLM, chat


# Confidence floor on the reranker score of the top chunk.
# bge-reranker-v2-m3 raw scores are unbounded; observed positive results were
# ~0.2 (weak) to ~0.99 (very strong). 0.1 is a permissive threshold that
# blocks only clearly off-topic top-1.
RERANK_FALLBACK_THRESHOLD = 0.1


_ANSWER_SYS = """너는 충남대학교 학내 정보 안내 챗봇이다.
주어진 [참고자료]만 사용해서 사용자 질문에 답변한다.

규칙 (엄수):
1. 절대 [참고자료]에 없는 정보를 추측·창작하지 않는다.
2. 학점·기간·금액 같은 숫자는 [참고자료]에 명시된 그대로만 인용한다.
3. 답변에는 가능한 한 근거 출처를 짧게 표시한다. 예: (출처: 학칙 제59조), (출처: 장학FAQ).
4. [참고자료]에서 답을 찾을 수 없거나 모호하면 "관련 정보를 찾지 못했습니다."라고만 답한다.
5. 답은 한국어로 간결하게. 평어/존댓말 일관. 머리말·인사·markdown 없이 본문만.
"""


@dataclass
class GenerationResult:
    answer: str
    used_fallback: bool
    top_rerank_score: float
    sources: list[dict]   # list of {chunk_id, title, source_url}


def _format_context(chunks: list, max_chunks: int = 8) -> str:
    """Format reranked chunks into a numbered context block for the LLM."""
    lines: list[str] = []
    for i, c in enumerate(chunks[:max_chunks], 1):
        m = c.meta or {}
        title = (m.get("source_title") or "").strip()
        body = (m.get("text") or m.get("_passage") or "").strip()
        if not body:
            continue
        lines.append(f"[{i}] 제목: {title}")
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
    """Generate an answer constrained to `reranked` chunks.

    Returns GenerationResult with fallback flag set when top-1 rerank score is
    below `fallback_threshold` — we refuse rather than hallucinate.
    """
    if not reranked:
        return GenerationResult(
            answer="관련 정보를 찾지 못했습니다.",
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
            answer="관련 정보를 찾지 못했습니다.",
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
