"""BM25 query tokenizer.

MUST match the tokenizer used at index build time
(crawler/phase_c/index_bm25.py: kiwipiepy + KEEP_POS).
Otherwise BM25 scores degrade due to vocabulary mismatch.
"""
from __future__ import annotations

from functools import lru_cache

from kiwipiepy import Kiwi

KEEP_POS = {
    "NNG", "NNP", "NNB", "NR", "NP",
    "VV", "VA", "VX", "VCP", "VCN",
    "XR",
    "SL", "SN", "SH",
}


@lru_cache(maxsize=1)
def _kiwi() -> Kiwi:
    return Kiwi()


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _kiwi().tokenize(text or ""):
        if tok.tag in KEEP_POS and tok.form:
            form = tok.form
            if form.isascii():
                form = form.lower()
            if len(form) == 1 and tok.tag == "SN":
                continue
            out.append(form)
    return out
