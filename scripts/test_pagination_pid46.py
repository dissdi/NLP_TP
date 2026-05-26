"""scripts/test_pagination_pid46.py — viewer 페이지 넘김 자동화 PoC.

paramItemId=46 (학과 100+, viewer 7 페이지)에서:
1. 일반 흐름으로 viewer popup 띄우기
2. popup 안의 모든 img/button/a 요소 분석 (next 버튼 후보 발견)
3. next 후보 클릭 → 새 XHR 응답 캡쳐 가능 여부 검증
4. 가능하면 마지막 페이지까지 순차 클릭 → 모든 응답 합산
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

SCHL = "0000029"
PID = "46"
YEAR = "2025"
LIST_URL = (
    f"https://www.academyinfo.go.kr/pubinfo/pubinfo0020/list.do"
    f"?schlId={SCHL}&svyYr={YEAR}&pageIdx=all&filePath=01&fileName=01&saveName=01"
)


def main():
    out_dir = ROOT / "data" / "spike_ubireport"
    out_dir.mkdir(parents=True, exist_ok=True)
    captures = []

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(locale="ko-KR", viewport={"width": 1600, "height": 900})

        def on_resp(r):
            if any(k in r.url for k in ("NewAcInfo.do", "UbiServer.do")):
                try:
                    b = r.body()
                except Exception:
                    return
                captures.append({"url": r.url, "len": len(b), "body": b.decode("utf-8", errors="replace")})
                print(f"  [CAPTURE] {len(b):,}B {r.url}")

        def attach(p):
            p.on("response", on_resp)

        ctx.on("page", attach)
        page = ctx.new_page()
        attach(page)

        try:
            page.goto(LIST_URL, wait_until="networkidle", timeout=60_000)
        except Exception:
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)

        sel = f"[onclick*=\"fn_RdViewer('{PID}','{YEAR}')\"]"
        with ctx.expect_page(timeout=15_000) as pi:
            page.locator(sel).first.click()
        popup = pi.value
        attach(popup)
        try:
            popup.wait_for_load_state("networkidle", timeout=60_000)
        except Exception:
            pass
        time.sleep(5)

        print(f"\n[1] page1 captures so far: {len(captures)}")

        # popup의 UI element 진단
        print(f"\n[2] popup UI element 분석 ===")
        ui_info = popup.evaluate("""
() => {
  const out = [];
  // img 요소
  for (const img of document.querySelectorAll('img')) {
    const src = img.getAttribute('src') || '';
    const alt = img.getAttribute('alt') || '';
    const title = img.getAttribute('title') || '';
    const onclick = img.getAttribute('onclick') || (img.parentElement?.getAttribute('onclick')) || '';
    if (/(next|prev|first|last|previous|page)/i.test(src + alt + title) ||
        /(다음|이전|페이지)/.test(alt + title)) {
      out.push({tag: 'img', src: src.split('/').slice(-1)[0], alt, title, onclick: onclick.slice(0, 100)});
    }
  }
  // button / a
  for (const b of document.querySelectorAll('button, a')) {
    const t = (b.innerText || b.textContent || '').trim().slice(0, 30);
    const onclick = b.getAttribute('onclick') || '';
    if (/(next|prev|first|last|page|다음|이전|페이지)/i.test(t + onclick)) {
      out.push({tag: b.tagName, text: t, onclick: onclick.slice(0, 100)});
    }
  }
  // 모든 onclick 함수명 후보
  const fnNames = new Set();
  for (const e of document.querySelectorAll('[onclick]')) {
    const oc = e.getAttribute('onclick') || '';
    const m = oc.match(/(\\w+)\\s*\\(/);
    if (m) fnNames.add(m[1]);
  }
  return { elements: out, onclick_fns: [...fnNames] };
}
        """)
        print(f"  matching elements: {len(ui_info['elements'])}")
        for e in ui_info["elements"][:20]:
            print(f"    {e}")
        print(f"  onclick fn names: {ui_info['onclick_fns']}")

        # next 시도 1: img click
        print(f"\n[3] 다음 페이지 시도 ===")
        next_selectors = [
            "img[src*='next.png']",
            "img[src*='next_d.png']",  # disabled
            "img[alt*='다음']",
            "img[title*='다음']",
            "[onclick*='next']",
            "[onclick*='goPage']",
        ]
        clicked = False
        before_n = len(captures)
        for s in next_selectors:
            cnt = popup.locator(s).count()
            print(f"  selector {s!r}: {cnt} matches")
            if cnt > 0:
                try:
                    popup.locator(s).first.click()
                    print(f"    clicked {s!r}")
                    clicked = True
                    time.sleep(5)
                    break
                except Exception as e:
                    print(f"    click fail: {str(e)[:80]}")
        print(f"  captures after click attempt: {len(captures)} (was {before_n})")

        br.close()

    print(f"\n=== summary ===")
    print(f"total captures: {len(captures)}")
    for i, c in enumerate(captures):
        print(f"  #{i}: {c['len']:,}B {c['url']}")
        # 각 응답을 파일로
        ext = "xml" if "<Doc" in c["body"][:200] else "txt"
        (out_dir / f"pid46_page{i+1}.{ext}").write_text(c["body"], encoding="utf-8")
    print(f"saved to {out_dir}/pid46_page*.xml")


if __name__ == "__main__":
    main()
