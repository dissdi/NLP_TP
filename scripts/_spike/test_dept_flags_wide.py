"""scripts/test_dept_flags_wide.py — flag 값 광역 탐색.

사용자 정찰로 v1(신입생경쟁률), v6(등록금?), v7(취업률) 발견.
나머지 3개 통계 (재학생수, 입학정원, 학생 1인당 장학금)의 flag 값 발견.

학과 약학과 (schlMjrId=0010025, mjrId=0022299).
"""
import sys
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "https://www.academyinfo.go.kr"
SCHL = "0000029"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

# 사용자 cURL의 약학과 ID
SCHL_MJR_ID = "0010025"
MJR_ID = "0022299"


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.7"})
    s.get(f"{BASE}/pubinfo/pubinfo1600/doInit.do", params={"schlId": SCHL}, timeout=20)
    s.get(f"{BASE}/pubinfo/pubinfo0081/doInit.do", timeout=20)

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Referer": f"{BASE}/pubinfo/pubinfo0081/doInit.do",
    }
    base_data = {
        "svyYr": "2026",  # 사용자 cURL은 2026 사용
        "schlMjrId": SCHL_MJR_ID, "schlId": SCHL, "mjrId": MJR_ID,
        "tabSelect": "d1",
        "schlMjrIdSe": SCHL_MJR_ID, "schlIdSe": SCHL, "mjrIdSe": MJR_ID,
        "mjrIdDt": "", "mjrNm": "undefined", "schNm": "충남대학교",
        "col1": "장학금", "col2": "등록금", "col3": "취업률",
        "col4": "교원 1인당 학생", "col5": "재학생수",  # 사용자 cURL: 재정학생수 → 재학생수로 시도
        "title": "",
        **{f"header{i}": "" for i in range(1, 10)},
    }

    print(f"=== flag 광역 탐색 (약학과 {SCHL_MJR_ID}/{MJR_ID}, svyYr=2026) ===")
    flags_to_try = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10",
                    "v11", "v12", "v13", "v14", "v15"]
    interesting = []

    for flag in flags_to_try:
        data = {**base_data, "flag": flag}
        url = f"{BASE}/pubinfo/pubinfo0081/selectFreshStudentRate.do"
        try:
            r = s.post(url, data=data, headers=headers, timeout=15)
        except Exception as e:
            print(f"  flag={flag}: error {e}")
            continue

        if r.status_code != 200:
            print(f"  flag={flag}: status {r.status_code}")
            continue
        try:
            js = r.json()
        except Exception:
            print(f"  flag={flag}: not JSON, body[:200]={r.text[:200]!r}")
            continue
        rl = js.get("resultList", [])
        if not rl:
            print(f"  flag={flag}: empty (len={len(r.text)}B)")
            continue
        first = rl[0]
        keys = list(first.keys())
        sample = json.dumps(first, ensure_ascii=False)
        print(f"  flag={flag}: n_entries={len(rl)} keys={keys} sample={sample[:150]}")
        interesting.append({
            "flag": flag, "n_entries": len(rl),
            "keys": keys, "sample": sample[:300],
            "all_entries": rl,
        })

    out = ROOT / "data" / "spike_ubireport" / "dept_flags_wide_result.json"
    out.write_text(json.dumps(interesting, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {out}")
    print(f"distinct non-empty flags: {len(interesting)}")


if __name__ == "__main__":
    sys.exit(main() or 0)
