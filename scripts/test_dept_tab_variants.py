"""scripts/test_dept_tab_variants.py — 탭 파라미터 변형 자동 시도.

학과 페이지의 6개 탭이 같은 endpoint(selectFreshStudentRate.do, selectList.do)를
다른 form data로 호출. tabSelect / flag / col1~col5 등 파라미터를 변형하며
어느 조합이 어떤 통계 데이터를 주는지 확인.

target: 약학과 (사용자 스크린샷의 학과)
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


def setup():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.7"})
    s.get(f"{BASE}/pubinfo/pubinfo1600/doInit.do", params={"schlId": SCHL}, timeout=20)
    s.get(f"{BASE}/pubinfo/pubinfo0081/doInit.do", timeout=20)
    return s


def find_target_dept(s):
    """약학과 또는 첫 학과 찾기."""
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Referer": f"{BASE}/pubinfo/pubinfo1600/doInit.do?schlId={SCHL}",
    }
    data = {
        "svyYr": "2025", "schlId": SCHL, "pulYn": "true",
        "schl_div_cd": "02", "schl_knd_cd": "03",
        "schlMjrId": "", "mjrId": "", "mjrNm": "", "schNm": "",
        "stsCode": "", "pageIdx": "", "dgHtDivCdArr": "",
        "schMjrCharCdArr": "", "schTxt": "",
        "srsLclftCd": "", "srsMclftCd": "", "srsSclftCd": "",
    }
    r = s.post(f"{BASE}/pubinfo/pubinfo1600/selectMjrList.do", data=data, headers=headers, timeout=30)
    rl = r.json().get("resultList", [])
    # 약학과 찾기
    target = next((m for m in rl if "약학" in m.get("mjr_nm", "")), None) or rl[0]
    return target


def try_variants(s, target):
    """다양한 tabSelect/flag 조합으로 호출 + 응답 저장."""
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Referer": f"{BASE}/pubinfo/pubinfo0081/doInit.do",
    }
    base_data = {
        "svyYr": "2025",
        "schlMjrId": target["schl_mjr_id"], "schlId": SCHL,
        "mjrId": target["mjr_id"],
        "schlMjrIdSe": target["schl_mjr_id"], "schlIdSe": SCHL,
        "mjrIdSe": target["mjr_id"],
        "mjrIdDt": "", "mjrNm": target.get("mjr_nm", ""),
        "schNm": "충남대학교",
        "col1": "장학금", "col2": "등록금", "col3": "취업률",
        "col4": "교원 1인당 학생", "col5": "재정학생수",
        "title": "",
        **{f"header{i}": "" for i in range(1, 10)},
    }

    endpoints = ["selectFreshStudentRate.do", "selectList.do"]
    results = {}
    print(f"\n=== Variants for {target.get('mjr_nm', '?')} ===")

    for ep in endpoints:
        for flag in ["v1", "v2", "v3", "v4", "v5", "v6"]:
            for tab in ["d1", "d2", "d3", "d4", "d5", "d6"]:
                data = {**base_data, "flag": flag, "tabSelect": tab}
                url = f"{BASE}/pubinfo/pubinfo0081/{ep}"
                try:
                    r = s.post(url, data=data, headers=headers, timeout=15)
                    body = r.text
                except Exception as e:
                    body = f"ERROR: {e}"
                # 응답 본문 분석
                if r.status_code == 200 and len(body) > 50:
                    try:
                        js = json.loads(body)
                        rl = js.get("resultList", [])
                        # entry 내용 다른지 첫 entry로 식별
                        key = f"{ep}|flag={flag}|tab={tab}"
                        first_keys = list(rl[0].keys())[:8] if rl else []
                        first_vals = list(rl[0].values())[:5] if rl else []
                        results[key] = {
                            "n_entries": len(rl),
                            "len": len(body),
                            "first_keys": first_keys,
                            "first_sample": json.dumps(rl[0], ensure_ascii=False)[:300] if rl else "",
                        }
                    except Exception:
                        pass
    return results


def main():
    out_dir = ROOT / "data" / "spike_ubireport"
    out_dir.mkdir(parents=True, exist_ok=True)
    s = setup()
    target = find_target_dept(s)
    print(f"target: {target.get('mjr_nm')} mjr_id={target.get('mjr_id')} schl_mjr_id={target.get('schl_mjr_id')}")

    results = try_variants(s, target)
    # 유의미한 응답만 출력 (entries > 0 또는 다른 keys)
    seen_signatures = set()
    print(f"\n=== Distinct response signatures ===")
    for key, v in results.items():
        sig = (tuple(v["first_keys"]), v["n_entries"])
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        print(f"\n{key}")
        print(f"  n_entries={v['n_entries']} len={v['len']:,}")
        print(f"  keys: {v['first_keys']}")
        print(f"  sample: {v['first_sample']}")

    out_path = out_dir / "dept_variants_result.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {len(results)} variants 시도, distinct {len(seen_signatures)}개")
    print(f"saved: {out_path}")


if __name__ == "__main__":
    sys.exit(main() or 0)
