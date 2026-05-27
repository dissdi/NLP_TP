"""scripts/sprint3/dorm_dstat_to_chunks.py — 기숙사 D-통계 4 pid를 표준 청크로 변환.

데이터 소스: data/sprint3/dstat/*.{records.json, xml}  (이미 어댑터 F로 수집됨)
출력:        data/sprint3/dstat/chunks.jsonl  (Phase C 입력 호환, 16-필드)

처리 정책:
  pid193 (수용 현황, 17 rec): row 0~1 헤더 skip → 건물별 자연어 청크 (15건 예상)
  pid266 (납부 방식, 3 rec):  row 0 헤더 skip → 형태별 청크 (2건 예상)
  pid262 (운영결과 민자):     XML Item 평탄 시퀀스 → 단일 청크 (헤더×값 짝)
  pid278 (운영결과 직영):     XML Item 평탄 시퀀스 → 단일 청크

스키마: text/source_type/source_url/source_title/domains/chunk_index/categories/
        freshness/posted_at/parent_post_id/section_path/notes/lang/chunk_id/char_count/crawled_at
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sprint3" / "dstat"
SCHL_ID = "0000029"
YEAR = "2025"
SOURCE_BASE = "https://www.academyinfo.go.kr/pubinfo/pubinfo0020/list.do"

PID_META = {
    "193": ("기숙사 수용 현황", "5-가. 기숙사 수용 현황 (생활관)"),
    "266": ("기숙사비 납부 방식", "5-나. 기숙사비 카드납부 및 현금분할납부 실시 현황"),
    "262": ("기숙사 운영결과 (민자)", "5-다. 기숙사 운영결과 (국·공립 민자)"),
    "278": ("기숙사 운영결과 (직영)", "5-라. 기숙사 운영결과 (국·공립 직영)"),
}


def make_chunk(text: str, idx: int, pid: str, label: str, section: str) -> dict:
    """16-필드 표준 청크 생성."""
    text = text.strip()
    chunk_id = hashlib.sha1(f"dstat_pid{pid}_{idx}_{text[:50]}".encode()).hexdigest()[:16]
    return {
        "chunk_id": chunk_id,
        "chunk_index": idx,
        "parent_post_id": f"dstat_pid{pid}_{YEAR}",
        "source_url": f"{SOURCE_BASE}#schlId={SCHL_ID}&paramItemId={pid}&year={YEAR}",
        "source_title": f"대학알리미 D-통계 - {label} ({YEAR})",
        "source_type": "T6",
        "section_path": f"기숙사 > D-통계 > {section}",
        "text": text,
        "char_count": len(text),
        "lang": "ko",
        "posted_at": f"{YEAR}-09-24",   # CSV 헤더의 최종확인일자
        "crawled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "freshness": "dated",
        "domains": [4],
        "categories": ["4.7"],
        "notes": f"D-통계 pid={pid} schl_id={SCHL_ID}",
    }


def is_header_row(row: dict) -> bool:
    """헤더 행 판정: 값이 키 자체이거나 키 목록에 포함되어 있으면 헤더."""
    keys = set(row.keys())
    non_empty_vals = [v for v in row.values() if v]
    if not non_empty_vals:
        return True
    # 값이 키와 같거나 키 목록에 포함된 비율이 절반 이상이면 헤더
    header_like = sum(1 for v in non_empty_vals if v in keys)
    return header_like / len(non_empty_vals) >= 0.5


def chunk_pid193() -> list:
    """건물별 행 → 자연어 청크."""
    p = DATA_DIR / f"{SCHL_ID}_pid193_{YEAR}_records.json"
    recs = json.load(p.open(encoding="utf-8"))
    out = []
    idx = 0
    label, section = PID_META["193"]
    for r in recs:
        if is_header_row(r):
            continue
        # 건물 데이터 행 → 자연어 변환
        building = r.get("건물명", "").strip() or "(미상)"
        gubun = r.get("구분", "").strip()
        year_built = r.get("준공연도", "").strip()
        capacity = r.get("수용가능인원(B)", "").strip()
        cost_1 = r.get("1인실", "").strip()
        cost_2 = r.get("2인실", "").strip()
        cost_3 = r.get("3인실", "").strip()
        cost_4 = r.get("4인실 이상", "").strip()
        meal = r.get("의무식\n여부", "").strip()
        rooms = r.get("총 실수", "").strip()
        applicants = r.get("기숙사 지원자 수(D)", "").strip()
        compete = r.get("입사 경쟁률\n(E=D/B)", "").strip()
        memo = r.get("비고", "").strip()
        accept_rate = r.get("기숙사수용률\n(C=B/Ax100)", "").strip()
        students = r.get("재학생수(A)", "").strip()

        parts = [
            f"충남대학교 기숙사 {building} ({gubun}, {year_built}년 준공) {YEAR}년 현황.",
            f"총 실 수 {rooms}실, 수용 가능 인원 {capacity}명.",
        ]
        costs = []
        if cost_1 and cost_1 != "0": costs.append(f"1인실 {cost_1}원")
        if cost_2 and cost_2 != "0": costs.append(f"2인실 {cost_2}원")
        if cost_3 and cost_3 != "0": costs.append(f"3인실 {cost_3}원")
        if cost_4 and cost_4 != "0": costs.append(f"4인실 이상 {cost_4}원")
        if costs:
            parts.append(f"기숙사비(학기당): {', '.join(costs)}.")
        if meal:
            parts.append(f"의무식 여부: {meal}.")
        if applicants and compete:
            parts.append(f"{YEAR}년 입사 지원자 {applicants}명, 입사 경쟁률 {compete}.")
        parts.append(f"학교 전체 재학생 {students}명 대비 기숙사 수용률 {accept_rate}%.")
        if memo:
            parts.append(f"비고: {memo}")

        text = " ".join(parts)
        out.append(make_chunk(text, idx, "193", label, section))
        idx += 1
    return out


def chunk_pid266() -> list:
    """납부 방식 행 → 청크."""
    p = DATA_DIR / f"{SCHL_ID}_pid266_{YEAR}_records.json"
    recs = json.load(p.open(encoding="utf-8"))
    out = []
    idx = 0
    label, section = PID_META["266"]
    for r in recs:
        if is_header_row(r):
            continue
        dorm_type = r.get("기숙사 형태", "").strip()
        card = r.get("카드납부 실시 여부", "").strip()
        installment = r.get("현금분할납부", "").strip()
        receipt = r.get("기숙사비 현금영수증 \n발급 실시 여부", "").strip()
        memo = r.get("비고", "").strip()
        parts = [
            f"충남대학교 본교(대전유성) {dorm_type} 기숙사 {YEAR}년 기숙사비 납부 방식.",
            f"카드납부: {card}.",
            f"현금분할납부: {installment}회.",
            f"기숙사비 현금영수증 발급: {receipt}.",
        ]
        if memo:
            parts.append(f"비고: {memo}")
        text = " ".join(parts)
        out.append(make_chunk(text, idx, "266", label, section))
        idx += 1
    return out


def chunk_pid_flat(pid: str) -> list:
    """pid262/278 평탄 XML: 안전한 raw dump 방식.

    페어링이 부정확하면 잘못된 fact을 답하게 됨 (high-stakes 비허용).
    헤더 항목과 값 항목을 분리해서 나열만 하고, LLM이 자체 매핑 시도하지 않도록
    '항목명들' / '수치값들' 명확히 라벨링.
    """
    p = DATA_DIR / f"{SCHL_ID}_pid{pid}_{YEAR}.xml"
    tree = ET.parse(p)
    root = tree.getroot()
    items = root.findall(".//Item")
    texts = [(item.findtext("Text") or item.findtext(".//Text") or "").strip() for item in items]
    texts = [t for t in texts if t]

    label, section = PID_META[pid]
    # 작성자·확인자·단위 메타 제거
    SKIP_PREFIX = ("ㆍ작성자", "ㆍ확인자", "ㆍ최종확인일자", "(단위", "ㆍ")
    texts = [t for t in texts if not t.startswith(SKIP_PREFIX)]
    # 제목 라벨 (첫 항목)도 별도 분리
    if texts and "[" in texts[0]:
        texts = texts[1:]

    # 항목명(텍스트) vs 수치값 분리
    def is_number(s: str) -> bool:
        s2 = s.replace(",", "").replace(".", "").strip()
        return bool(s2) and s2.isdigit()
    headers = [t for t in texts if not is_number(t)]
    values = [t for t in texts if is_number(t)]

    # 안전한 dump: 페어링 안 함
    body = (
        f"보고 항목: {', '.join(headers)}. "
        f"보고 수치(원, 항목 순서 비보장): {', '.join(values)}."
    )
    text = (
        f"충남대학교 {label} ({YEAR}년) 알리미 D-통계 원본 데이터. "
        f"학생생활관 작성, 최종확인 2025-09-24. {body} "
        f"※ 항목과 수치의 1:1 매핑은 원본 표(알리미 사이트)를 참조하세요."
    )
    return [make_chunk(text, 0, pid, label, section)]


def main():
    all_chunks = []
    all_chunks.extend(chunk_pid193())
    all_chunks.extend(chunk_pid266())
    all_chunks.extend(chunk_pid_flat("262"))
    all_chunks.extend(chunk_pid_flat("278"))

    out_path = DATA_DIR / "chunks.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    # manifest 갱신
    manifest = {
        "schl_id": SCHL_ID,
        "year": YEAR,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "source": "어댑터 F (UbiReport) 수집 산출물 → 표준 청크 변환",
        "pids": list(PID_META.keys()),
        "n_chunks_total": len(all_chunks),
        "per_pid": {},
    }
    for pid in PID_META:
        manifest["per_pid"][pid] = sum(1 for c in all_chunks if f"pid={pid}" in c.get("notes", ""))

    (DATA_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"=== 변환 완료 ===")
    print(f"  total chunks: {len(all_chunks)}")
    for pid in PID_META:
        print(f"    pid{pid}: {manifest['per_pid'][pid]} chunks")
    print(f"  chunks:  {out_path}")
    print(f"  manifest: {DATA_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
