"""scripts/test_dept_api_probe.py — 학과정보 API endpoint 응답 본문 진단.

cURL 정찰로 발견한 3개 endpoint를 직접 호출 + 응답 저장:
  pubinfo1600/selectMjrList.do
  pubinfo0081/selectFreshStudentRate.do
  pubinfo0081/selectList.do

svyYr 2026/2025/2024 모두 시도 (2026은 미공시일 가능성).
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


def setup_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.7",
    })
    # 세션 쿠키 확보 (doInit 페이지들 GET)
    print("[setup] GET pubinfo1600/doInit ...")
    r = s.get(f"{BASE}/pubinfo/pubinfo1600/doInit.do", params={"schlId": SCHL}, timeout=20)
    print(f"  status={r.status_code} cookies={list(s.cookies.keys())}")
    print("[setup] GET pubinfo0081/doInit ...")
    r = s.get(f"{BASE}/pubinfo/pubinfo0081/doInit.do", timeout=20)
    print(f"  status={r.status_code}")
    return s


def call_select_mjr_list(s: requests.Session, year: str) -> list[dict]:
    print(f"\n[1] selectMjrList.do (year={year})")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Referer": f"{BASE}/pubinfo/pubinfo1600/doInit.do?schlId={SCHL}",
    }
    data = {
        "svyYr": year, "schlId": SCHL, "pulYn": "true",
        "schl_div_cd": "02", "schl_knd_cd": "03",
        "schlMjrId": "", "mjrId": "", "mjrNm": "", "schNm": "",
        "stsCode": "", "pageIdx": "", "dgHtDivCdArr": "",
        "schMjrCharCdArr": "", "schTxt": "",
        "srsLclftCd": "", "srsMclftCd": "", "srsSclftCd": "",
    }
    r = s.post(f"{BASE}/pubinfo/pubinfo1600/selectMjrList.do", data=data, headers=headers, timeout=30)
    print(f"  status={r.status_code} len={len(r.text):,}")
    if r.status_code != 200:
        return []
    js = r.json()
    rl = js.get("resultList", [])
    print(f"  resultList: {len(rl)} entries")
    if rl:
        f = rl[0]
        print(f"  first: mjr_id={f.get('mjr_id')} schl_mjr_id={f.get('schl_mjr_id')} "
              f"mjr_nm={f.get('mjr_nm')} clg_nm={f.get('clg_nm')}")
    return rl


def call_fresh_rate(s: requests.Session, year: str, mjr_id: str, schl_mjr_id: str) -> dict:
    print(f"\n[2] selectFreshStudentRate.do (year={year}, mjr={mjr_id})")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Referer": f"{BASE}/pubinfo/pubinfo0081/doInit.do",
    }
    data = {
        "svyYr": year,
        "schlMjrId": schl_mjr_id, "schlId": SCHL, "mjrId": mjr_id,
        "flag": "v1", "tabSelect": "d1",
        "schlMjrIdSe": schl_mjr_id, "schlIdSe": SCHL, "mjrIdSe": mjr_id,
        "mjrIdDt": "", "mjrNm": "undefined", "schNm": "충남대학교",
        "col1": "장학금", "col2": "등록금", "col3": "취업률",
        "col4": "교원 1인당 학생", "col5": "재정학생수",
        "title": "",
        **{f"header{i}": "" for i in range(1, 10)},
    }
    r = s.post(f"{BASE}/pubinfo/pubinfo0081/selectFreshStudentRate.do",
               data=data, headers=headers, timeout=30)
    print(f"  status={r.status_code} len={len(r.text):,}")
    if r.status_code != 200:
        return {}
    js = r.json()
    rl = js.get("resultList", [])
    print(f"  resultList: {len(rl)} entries")
    if rl:
        print(f"  first entry keys: {list(rl[0].keys())[:15]}")
        print(f"  first entry sample: {json.dumps(rl[0], ensure_ascii=False)[:500]}")
    return js


def call_select_list(s: requests.Session, year: str, mjr_id: str, schl_mjr_id: str) -> dict:
    print(f"\n[3] selectList.do (year={year}, mjr={mjr_id})")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Referer": f"{BASE}/pubinfo/pubinfo0081/doInit.do",
    }
    data = {
        "svyYr": year,
        "schlMjrId": schl_mjr_id, "schlId": SCHL, "mjrId": mjr_id,
        "flag": "v1", "tabSelect": "d1",
        "schlMjrIdSe": schl_mjr_id, "schlIdSe": SCHL, "mjrIdSe": mjr_id,
        "mjrIdDt": "", "mjrNm": "undefined", "schNm": "충남대학교",
        "col1": "장학금", "col2": "등록금", "col3": "취업률",
        "col4": "교원 1인당 학생", "col5": "재정학생수",
        "title": "",
        **{f"header{i}": "" for i in range(1, 10)},
    }
    r = s.post(f"{BASE}/pubinfo/pubinfo0081/selectList.do",
               data=data, headers=headers, timeout=30)
    print(f"  status={r.status_code} len={len(r.text):,}")
    if r.status_code != 200:
        return {}
    js = r.json()
    rl = js.get("resultList", [])
    print(f"  resultList: {len(rl)} entries")
    if rl:
        print(f"  first entry keys: {list(rl[0].keys())[:15]}")
        print(f"  first entry sample: {json.dumps(rl[0], ensure_ascii=False)[:500]}")
    return js


def main():
    out_dir = ROOT / "data" / "spike_ubireport"
    out_dir.mkdir(parents=True, exist_ok=True)
    s = setup_session()

    # 우선 학과 메타 (year 2025로)
    mjrs = call_select_mjr_list(s, "2025")
    if not mjrs:
        # 다른 year 시도
        for y in ["2024", "2026"]:
            mjrs = call_select_mjr_list(s, y)
            if mjrs:
                break
    if not mjrs:
        print("[FATAL] no major list")
        return 2

    # 컴퓨터인공지능학부 (사용자 정찰의 학과) 찾기 + 첫 학과 사용
    target = next((m for m in mjrs if m.get("schl_mjr_id") == "0252842"), mjrs[0])
    print(f"\n[target] {target.get('mjr_nm')} mjr_id={target.get('mjr_id')} schl_mjr_id={target.get('schl_mjr_id')}")

    # 5개 통계 API 시도 - 여러 svyYr로
    results = {}
    for y in ["2025", "2024", "2026"]:
        print(f"\n{'='*60}\n=== svyYr={y} ===")
        rate = call_fresh_rate(s, y, target["mjr_id"], target["schl_mjr_id"])
        lst = call_select_list(s, y, target["mjr_id"], target["schl_mjr_id"])
        results[y] = {
            "freshRate": rate, "selectList": lst,
        }

    out_path = out_dir / "dept_api_probe_result.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {out_path}")


if __name__ == "__main__":
    sys.exit(main() or 0)
