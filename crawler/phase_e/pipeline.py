"""End-to-end RAG pipeline: hybrid retrieve -> rerank -> generate.

Adds tool routing in front: if a query keyword matches a registered tool
(see crawler.phase_e.tools), the tool fetches fresh data and we skip RAG.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .generate import GenerationResult, generate_answer
from .llm import DEFAULT_4BIT, DEFAULT_LLM, chat
from .reranker import rerank
from .retriever import HybridRetriever, build_default
from .query_expand import expand_query
from .tools import maybe_use_tool


@dataclass
class AnswerResult(GenerationResult):
    query: str = ""
    retrieval_pool: int = 0
    rerank_top_k: int = 0
    used_tool: str = ""


class RAGPipeline:
    def __init__(self, retriever: Optional[HybridRetriever] = None):
        self.retriever = retriever or build_default()

    def answer(
        self,
        query: str,
        bm25_pool: int = 100,
        dense_pool: int = 50,
        retrieve_top_k: int = 30,
        rerank_top_k: int = 8,
        max_new_tokens: int = 512,
        enable_expand: bool = False,
    ) -> AnswerResult:
        # 1) Tool routing first (real-time data trumps static corpus for dynamic questions)
        tool_hit = maybe_use_tool(query)
        if tool_hit is not None:
            tool_name, tr = tool_hit
            return self._answer_with_tool(query, tool_name, tr, max_new_tokens)

        # 2) Standard RAG path. expand_query default OFF — caused -16% on D-1 eval.
        # Useful only for slang/abbrev user queries; opt-in via enable_expand=True.
        expanded = expand_query(query) if enable_expand else query
        pool = self.retriever.retrieve(
            expanded,
            top_k=retrieve_top_k,
            bm25_pool=bm25_pool,
            dense_pool=dense_pool,
        )
        # Rerank with the ORIGINAL query so cross-encoder evaluates real intent
        hits = rerank(query, pool, top_k=rerank_top_k)
        gen = generate_answer(
            query,
            hits,
            max_chunks=rerank_top_k,
            max_new_tokens=max_new_tokens,
        )
        return AnswerResult(
            query=query,
            retrieval_pool=len(pool),
            rerank_top_k=rerank_top_k,
            answer=gen.answer,
            used_fallback=gen.used_fallback,
            top_rerank_score=gen.top_rerank_score,
            sources=gen.sources,
            used_tool="",
        )

    def _answer_with_tool(self, query: str, tool_name: str, tr: dict, max_new_tokens: int) -> AnswerResult:
        """Build LLM context from the tool result, generate answer with the same prompt rules."""
        from .generate import _ANSWER_SYS, _USER_TEMPLATE
        context = tr["context"]
        user_msg = _USER_TEMPLATE.format(query=query, context=context)
        answer = chat(
            user_msg=user_msg,
            system_msg=_ANSWER_SYS,
            model_id=DEFAULT_LLM,
            load_in_4bit=DEFAULT_4BIT,
            max_new_tokens=max_new_tokens,
            temperature=0.0,
        )
        return AnswerResult(
            query=query,
            retrieval_pool=0,
            rerank_top_k=0,
            answer=answer.strip(),
            used_fallback=False,
            top_rerank_score=1.0,
            sources=tr.get("sources") or [],
            used_tool=tool_name,
        )
