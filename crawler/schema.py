"""청크 메타데이터 스키마 (crawling-targets.md §12 기준).

16 필드 JSON Lines 형식.
어댑터들은 이 스키마를 채워서 출력한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# crawling-targets.md §1의 T1~T6
SOURCE_TYPES = {"T1", "T2", "T3", "T4", "T5", "T6"}

# §11-2 cross 그룹: 9도메인 정수 코드
VALID_DOMAINS = set(range(1, 10))

# §10·§11에 등장한 카테고리 코드 (확장 가능)
# 5.4 백마광장 백본 분류에 주로 사용
KNOWN_CATEGORIES: set[str] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stable_chunk_id(source_url: str, chunk_index: int, text: str) -> str:
    """source_url + chunk_index + text 해시로 안정적 chunk_id 생성."""
    h = hashlib.sha1()
    h.update(source_url.encode("utf-8"))
    h.update(b"|")
    h.update(str(chunk_index).encode("utf-8"))
    h.update(b"|")
    # 본문 일부만 해시 (전체는 비용 큼)
    h.update(text[:256].encode("utf-8"))
    return h.hexdigest()[:16]


@dataclass
class Chunk:
    """청크 1건 = JSON Lines 한 줄.

    필수 (어댑터에서 반드시 채움):
      text, source_type, source_url, source_title, domains
    파생 (헬퍼가 채움):
      chunk_id, char_count, crawled_at, lang
    선택 (정보 있을 때만):
      categories, freshness, posted_at, parent_post_id, section_path, notes
    """

    text: str
    source_type: str
    source_url: str
    source_title: str
    domains: list[int]
    chunk_index: int = 0

    categories: list[str] = field(default_factory=list)
    freshness: Optional[str] = None  # "static" / "dated" / "rolling"
    posted_at: Optional[str] = None  # 게시물 작성일
    parent_post_id: Optional[str] = None
    section_path: Optional[str] = None  # 예: "h2:학사일정 > h3:1학기"
    notes: Optional[str] = None
    lang: str = "ko"

    chunk_id: str = field(default="")
    char_count: int = 0
    crawled_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        # 정규화
        self.text = _normalize_text(self.text)
        self.char_count = len(self.text)

        if not self.chunk_id:
            self.chunk_id = _stable_chunk_id(self.source_url, self.chunk_index, self.text)

        # 검증
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"invalid source_type: {self.source_type}")
        if not self.domains or not all(d in VALID_DOMAINS for d in self.domains):
            raise ValueError(f"invalid domains: {self.domains}")
        if self.char_count == 0:
            raise ValueError("empty text")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# --- 텍스트 정규화 ---

_WS_RE = re.compile(r"[ \t ]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _normalize_text(s: str) -> str:
    if not s:
        return ""
    # 공백 정규화
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _WS_RE.sub(" ", s)
    # 라인 trim
    s = "\n".join(line.strip() for line in s.split("\n"))
    # 3+ 줄바꿈 → 2개
    s = _MULTI_NL_RE.sub("\n\n", s)
    return s.strip()


def write_jsonl(chunks: list[Chunk], path: str) -> int:
    """JSON Lines 파일 저장. 작성된 라인 수 반환."""
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(c.to_json_line() + "\n")
            n += 1
    return n
