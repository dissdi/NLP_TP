"""Query rewriting + HyDE (deprioritized — see project-nlp-tp-phase-e-strategy).

Smoke test showed 4B LLM hallucinations made retrieval WORSE on 2/7 queries.
Kept as opt-in; default pipeline does not call these.
"""
from __future__ import annotations

from typing import Optional

from .llm import DEFAULT_LLM, chat


_REWRITE_SYS = """너는 충남대학교 학내 정보 검색 시스템의 질의 정제기다.
사용자 질문을 학칙·공지·학과 안내문 검색에 잘 맞도록 다시 쓴다.

규칙:
- 학과 약어를 정식 명칭으로 풀어라 (예: 컴공 -> 컴퓨터인공지능학부, 전기과 -> 전기공학과).
- 일상어를 학칙·행정 용어로 바꿔라 (예: 쉬다 -> 휴학, 학교 그만두다 -> 자퇴).
- 핵심 키워드(학점/기간/절차/대상/금액)는 명확히 남겨라.
- 결과는 한 줄, 한국어, 따옴표/머리말/prefix 없이만 출력.
"""

_HYDE_SYS = """너는 충남대학교 학내 정보 답변 작성자다.
사용자 질문에 대해 학칙·공지·학과 안내의 톤으로 그럴듯한 답변 문단을 한국어로 작성한다.

규칙:
- 2~4문장, 학칙/안내 본문 같은 어투.
- 머리말·인사·markdown 금지. 본문만.
"""


def rewrite_query(query: str, model_id: str = DEFAULT_LLM, load_in_4bit: Optional[bool] = None) -> str:
    kwargs = {"load_in_4bit": load_in_4bit} if load_in_4bit is not None else {}
    out = chat(
        user_msg=query,
        system_msg=_REWRITE_SYS,
        model_id=model_id,
        max_new_tokens=80,
        temperature=0.0,
        **kwargs,
    )
    for line in out.splitlines():
        line = line.strip().strip('"').strip("'")
        if line:
            return line
    return query


def hyde_query(query: str, model_id: str = DEFAULT_LLM, load_in_4bit: Optional[bool] = None) -> str:
    kwargs = {"load_in_4bit": load_in_4bit} if load_in_4bit is not None else {}
    out = chat(
        user_msg=query,
        system_msg=_HYDE_SYS,
        model_id=model_id,
        max_new_tokens=200,
        temperature=0.0,
        **kwargs,
    )
    return out.strip()
