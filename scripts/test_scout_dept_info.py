"""scripts/test_scout_dept_info.py — 학과정보 진입점 자동 정찰.

알리미 충남대 학과정보 페이지 (pubinfo1600/doInit.do)의 UI 구조 분석:
  1. 학과 리스트 추출 (101개 학과 expected)
  2. 보고서 항목 리스트 추출
  3. 학과+보고서 선택 시 발생하는 XHR endpoint 패턴
  4. 자동화 가능 여부 결론

결과를 콘솔 + data/spike_ubireport/dept_info_scout.json 에 저장.
"""
import sys
import json
import time
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

SCHL = "0000029"
DEPT_URL = f"https://www.academyinfo.go.kr/pubinfo/pubinfo1600/doInit.do?schlId={SCHL}"


def main():
    out_dir = ROOT / "data" / "spike_ubireport"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    captures = []

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(locale="ko-KR", viewport={"width": 1600, "height": 900})

        def on_resp(r):
            if any(k in r.url for k in (
                "NewAcInfo.do", "UbiServer.do", "RdViewer.do",
                "pubinfo1600", "deptList", "deptInfo", "Dept"
            )):
                try:
                    body_text = ""
                    if r.status == 200:
                        try:
                            body_text = r.body().decode("utf-8", errors="replace")[:1500]
                        except Exception:
                            pass
                    captures.append({
                        "url": r.url, "status": r.status,
                        "ct": r.headers.get("content-type", "")[:50],
                        "body_head": body_text[:500],
                    })
                except Exception:
                    pass

        def attach(p):
            p.on("response", on_resp)

        ctx.on("page", attach)
        page = ctx.new_page()
        attach(page)

        print(f"[1] Navigate to {DEPT_URL}")
        try:
            page.goto(DEPT_URL, wait_until="networkidle", timeout=60_000)
        except Exception:
            page.goto(DEPT_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)

        # 페이지 HTML 저장
        html = page.content()
        (out_dir / "dept_info_page.html").write_text(html, encoding="utf-8")
        summary["page_html_size"] = len(html)
        print(f"    page HTML: {len(html):,} chars  saved as dept_info_page.html")

        # 페이지 URL (redirect 후)
        print(f"    final URL: {page.url!r}")
        summary["final_url"] = page.url

        # 페이지 분석: 학과 리스트 추출 시도
        print(f"\n[2] UI element 분석")
        ui_info = page.evaluate(r"""
() => {
  const out = { selects: [], buttons: [], dept_options: [], fn_names: new Set() };

  // <select> 안의 option들 (학과 dropdown 가능성)
  for (const sel of document.querySelectorAll('select')) {
    const opts = [...sel.querySelectorAll('option')].map(o => ({
      value: o.value, text: o.innerText.trim().slice(0, 50)
    }));
    out.selects.push({
      id: sel.id, name: sel.name, n_options: opts.length, options: opts.slice(0, 10)
    });
  }

  // 학과명 같은 텍스트 (li, dt, a 등에서)
  const dept_kw = /[가-힣]+(학과|학부|전공)/;
  for (const el of document.querySelectorAll('li, dt, a, button, label, td')) {
    const t = (el.innerText || el.textContent || '').trim();
    if (dept_kw.test(t) && t.length < 40 && !out.dept_options.find(d => d.text === t)) {
      out.dept_options.push({ tag: el.tagName, text: t });
    }
  }

  // 버튼/링크의 onclick 함수명
  for (const el of document.querySelectorAll('[onclick]')) {
    const oc = el.getAttribute('onclick') || '';
    const m = oc.match(/(\w+)\s*\(/);
    if (m) out.fn_names.add(m[1]);
  }
  out.fn_names = [...out.fn_names];

  // [YYYY 보기] 패턴
  const view_btns = [];
  for (const el of document.querySelectorAll('a, button, span, input')) {
    const t = (el.innerText || el.value || '').trim();
    if (/^20\d{2}\s*보기$/.test(t)) {
      view_btns.push({
        tag: el.tagName, text: t,
        onclick: (el.getAttribute('onclick') || '').slice(0, 100)
      });
    }
  }
  out.view_btns_count = view_btns.length;
  out.view_btns_sample = view_btns.slice(0, 6);
  return out;
}
        """)
        summary["ui_info"] = ui_info
        print(f"    <select>: {len(ui_info['selects'])}")
        for s in ui_info['selects'][:3]:
            print(f"      id={s['id']!r} name={s['name']!r} n_options={s['n_options']}")
            for o in s['options'][:3]:
                print(f"        option: value={o['value']!r} text={o['text']!r}")
        print(f"    dept-like texts: {len(ui_info['dept_options'])}")
        for d in ui_info['dept_options'][:10]:
            print(f"      {d['tag']} {d['text']!r}")
        print(f"    onclick fn names: {ui_info['fn_names'][:20]}")
        print(f"    [YYYY 보기] buttons: {ui_info['view_btns_count']}")
        for b in ui_info['view_btns_sample'][:3]:
            print(f"      {b}")

        br.close()

    print(f"\n[3] captures during load ({len(captures)}):")
    for c in captures[:10]:
        print(f"    {c['status']} {c['ct']:30s} {c['url']}")
    summary["captures"] = captures

    (out_dir / "dept_info_scout.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nsaved: {out_dir / 'dept_info_scout.json'}")
    print(f"       {out_dir / 'dept_info_page.html'}")


if __name__ == "__main__":
    main()
