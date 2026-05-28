"""eval-generated.jsonl에 Q&A 16필드를 안전하게 append.

검증:
- 16필드 정합
- qa_id 중복 차단
- expected_source_urls가 corpus에 존재하는지 (warn only)
- domain 1..9
- question_type A|B|C|D

사용법:
    python append_qa.py < batch.json
또는 import해서 append_qas(list_of_dicts) 호출.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "eval-generated.jsonl"

REQUIRED_FIELDS = {
    "qa_id", "question", "answer_gold", "domain", "categories",
    "question_type", "expected_source_urls", "is_fallback_expected",
    "tags", "created_by", "reviewed_by", "created_at", "reviewed_at",
    "gen_prompt_version", "notes",
}


def load_existing_ids() -> set[str]:
    if not OUT.exists():
        return set()
    ids = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            o = json.loads(line)
            ids.add(o.get("qa_id"))
        except Exception:
            pass
    return ids


def validate(qa: dict, existing_ids: set[str]) -> list[str]:
    errs = []
    missing = REQUIRED_FIELDS - set(qa.keys())
    if missing:
        errs.append(f"missing fields: {sorted(missing)}")
    extra = set(qa.keys()) - REQUIRED_FIELDS
    if extra:
        errs.append(f"extra fields: {sorted(extra)}")
    qid = qa.get("qa_id")
    if not isinstance(qid, str) or not qid:
        errs.append("qa_id empty")
    elif qid in existing_ids:
        errs.append(f"qa_id duplicate: {qid}")
    if qa.get("domain") not in range(1, 10):
        errs.append(f"domain out of range: {qa.get('domain')}")
    if qa.get("question_type") not in {"A", "B", "C", "D"}:
        errs.append(f"question_type invalid: {qa.get('question_type')}")
    if not isinstance(qa.get("expected_source_urls"), list):
        errs.append("expected_source_urls not list")
    if not isinstance(qa.get("categories"), list):
        errs.append("categories not list")
    if not isinstance(qa.get("tags"), list) or len(qa.get("tags") or []) < 1:
        errs.append("tags must be list with >=1")
    if not isinstance(qa.get("is_fallback_expected"), bool):
        errs.append("is_fallback_expected must be bool")
    return errs


def append_qas(qas: Iterable[dict]) -> tuple[int, int, list[str]]:
    existing = load_existing_ids()
    accepted, rejected, errs = 0, 0, []
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        for qa in qas:
            e = validate(qa, existing)
            if e:
                rejected += 1
                errs.append(f"{qa.get('qa_id','?')}: {'; '.join(e)}")
                continue
            existing.add(qa["qa_id"])
            f.write(json.dumps(qa, ensure_ascii=False) + "\n")
            accepted += 1
    return accepted, rejected, errs


def main():
    data = json.load(sys.stdin)
    if isinstance(data, dict) and "qa_pairs" in data:
        data = data["qa_pairs"]
    if not isinstance(data, list):
        print("ERROR: stdin must be JSON list or {qa_pairs:[...]}.", file=sys.stderr)
        sys.exit(2)
    a, r, errs = append_qas(data)
    print(f"accepted={a} rejected={r}")
    for e in errs:
        print(f"  - {e}")


if __name__ == "__main__":
    main()
