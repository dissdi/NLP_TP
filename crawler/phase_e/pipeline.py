"""End-to-end RAG pipeline: hybrid retrieve -> rerank -> generate.

Usage:
  from crawler.phase_e.pipeline import RAGPipeline
  p = RAGPipeline()
  result = p.answer("졸업요건 학점은?")
  print(result.answer)
  for s in result.sources: print(s)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .generate import GenerationResult, generate_answer
from .reranker import rerank
from .retriever import HybridRetriever, build_default


@dataclass
class AnswerResult(GenerationResult):
    query: str = ""
    retrieval_pool: int = 0
    rerank_top_k: int = 0


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
    ) -> AnswerResult:
        pool = self.retriever.retrieve(
            query,
            top_k=retrieve_top_k,
            bm25_pool=bm25_pool,
            dense_pool=dense_pool,
        )
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
        )
