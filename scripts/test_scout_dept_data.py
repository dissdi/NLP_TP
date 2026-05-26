"""scripts/test_scout_dept_data.py — 학과 선택 후 데이터 endpoint 정찰.

selectMjrList.do로 학과 메타는 받았는데, 그 학과 선택 시 통계 데이터가
어떤 endpoint로 오는지 확인. fn_doSelect 호출 + 발생 XHR 캡쳐.
"""
import sys
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHL = "0000029"
URL = f"https://www.academyinfo.go.kr/pubinfo/pubinfo1600/doInit.do?schlId={SCHL}"


def main():
    out_dir = ROOT / "data" / "spike_ubireport"
    out_dir.mkdir(parents=True, exist_ok=True)
    captures = []
    mjr_full = None

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(locale="ko-KR", viewport={"width": 1600, "height": 900})

        def on_resp(r):
            try:
                ct = r.headers.get("content-type", "")
                body = ""
                if r.status == 200 and ("json" in ct or "xml" in ct or "text" in ct):
                    try:
                        body = r.body().decode("utf-8", errors="replace")
                    except Exception:
                        body = ""
                if any(k in r.url for k in (
                    "pubinfo1600", "selectMjr", "selectChart", "selectData",
                    "Detail", "Dept", "Mjr", "AcInfo", "UbiServer",
                )):
                    captures.append({
                        "url": r.url, "status": r.status, "ct": ct[:50],
                        "len": len(body), "body_head": body[:2000],
                    })
                    print(f"  [CAP] {r.status} {ct[:30]} {r.url}  ({len(body):,}B)")
            except Exception:
                pass

        def attach(p):
            p.on("response", on_resp)

        ctx.on("page", attach)
        page = ctx.new_page()
        attach(page)

        print(f"[1] Navigate to {URL}")
        try:
            page.goto(URL, wait_until="networkidle", timeout=60_000)
        except Exception:
            page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(4)

        # selectMjrList 응답 전체 저장
        for c in captures:
            if "selectMjrList" in c["url"]:
                try:
                    mjr_full = json.loads(c["body_head"])
                except Exception:
                    pass
        if mjr_full and "resultList" in mjr_full:
            print(f"\n[2] selectMjrList.do parsed: {len(mjr_full['resultList'])} entries")
            # 첫 학과 정보
            first = mjr_full["resultList"][0]
            print(f"    first: {first.get('kor_mjr_nm')} (mjr_id={first.get('mjr_id')})")
            (out_dir / "dept_mjr_list_sample.json").write_text(
                json.dumps(mjr_full["resultList"][:3], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # 페이지 element 동적 검사
        print(f"\n[3] DOM 학과 element 찾기")
        elem_info = page.evaluate(r"""
() => {
  const out = { mjr_clickable: [], mjr_listing: [] };
  // 클릭 가능한 학과 element (li/a/tr/td 등 + 학과명 텍스트 + click handler)
  const dept_pattern = /[가-힣]+(학과|학부|학)/;
  for (const el of document.querySelectorAll('li, a, tr, td, button, div[onclick]')) {
    const t = (el.innerText || el.textContent || '').trim();
    if (!t || t.length > 30) continue;
    if (dept_pattern.test(t)) {
      const oc = el.getAttribute('onclick') || '';
      const cls = el.className || '';
      out.mjr_listing.push({
        tag: el.tagName, text: t.slice(0, 30),
        cls: cls.slice(0, 50), onclick: oc.slice(0, 100)
      });
      if (oc || el.tagName === 'A' || cls.includes('mjr')) {
        out.mjr_clickable.push({tag: el.tagName, text: t.slice(0, 30), onclick: oc.slice(0, 100)});
      }
    }
  }
  // 처음 8개만
  out.mjr_listing = out.mjr_listing.slice(0, 8);
  out.mjr_clickable = out.mjr_clickable.slice(0, 8);
  return out;
}
        """)
        print(f"    학과 텍스트 있는 element ({len(elem_info['mjr_listing'])} found):")
        for e in elem_info['mjr_listing'][:5]:
            print(f"      {e}")
        print(f"    클릭 가능 학과 element ({len(elem_info['mjr_clickable'])}):")
        for e in elem_info['mjr_clickable'][:5]:
            print(f"      {e}")

        # 시도 1: fn_doSelect 직접 호출 (첫 학과 mjr_id)
        if mjr_full and mjr_full.get("resultList"):
            first_mjr = mjr_full["resultList"][0]
            mjr_id = first_mjr.get("mjr_id")
            schl_mjr_id = first_mjr.get("schl_mjr_id")
            print(f"\n[4] fn_doSelect('{mjr_id}') 또는 ('{schl_mjr_id}') 시도")
            captures.clear()  # 이전 captures 클리어
            for arg in [mjr_id, schl_mjr_id]:
                try:
                    result = page.evaluate(f"""
() => {{
  if (typeof window.fn_doSelect === 'function') {{
    try {{
      window.fn_doSelect('{arg}');
      return 'fn_doSelect_called_with_{arg}';
    }} catch(e) {{ return 'error: ' + e.message; }}
  }}
  return 'fn_doSelect_not_found';
}}
                    """)
                    print(f"    arg={arg}: {result}")
                    time.sleep(3)
                except Exception as e:
                    print(f"    arg={arg} eval fail: {e}")

        print(f"\n[5] captures after fn_doSelect ({len(captures)}):")
        for c in captures[:15]:
            print(f"    {c['status']} {c['ct'][:30]:30s} {c['len']:,}B  {c['url']}")

        # 시도 2: DOM에서 첫 클릭 가능 학과 element 클릭
        if elem_info['mjr_clickable']:
            print(f"\n[6] DOM 첫 학과 element 클릭 시도")
            try:
                # 첫 mjr_clickable의 텍스트로 locator
                first_text = elem_info['mjr_clickable'][0]['text']
                lo = page.get_by_text(first_text, exact=True).first
                if lo.count() > 0:
                    captures.clear()
                    lo.click()
                    time.sleep(5)
                    print(f"    clicked. captures: {len(captures)}")
                    for c in captures[:10]:
                        print(f"      {c['status']} {c['ct'][:30]:30s} {c['len']:,}B  {c['url']}")
            except Exception as e:
                print(f"    click fail: {e}")

        br.close()


if __name__ == "__main__":
    main()
