"""scripts/test_diagnose_pid46.py — paramItemId=46 popup의 모든 응답 캡쳐.

test_fetch_pid46.py는 NewAcInfo.do만 보는데, 이 스크립트는 popup의
모든 응답·요청을 캡쳐해서 paramItemId=46이 어떤 endpoint를 쓰는지 파악.
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCHL_ID = "0000029"
YEAR = "2025"
LIST_URL = (
    f"https://www.academyinfo.go.kr/pubinfo/pubinfo0020/list.do"
    f"?schlId={SCHL_ID}&svyYr={YEAR}"
    f"&pageIdx=all&filePath=01&fileName=01&saveName=01"
)


def diagnose(pid: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"=== diagnose pid={pid} ===")
    reqs, resps, popup_urls = [], [], []

    def on_req(r):
        if r.method == "POST" or any(k in r.url for k in [
            "RdViewer", "NewAcInfo", "pubinfo", "AcInfo", "Report",
            ".do?", "pdf", "download",
        ]):
            reqs.append((r.method, r.url, r.resource_type))

    def on_resp(r):
        ct = r.headers.get("content-type", "")[:40]
        if any(k in r.url for k in [
            "RdViewer", "NewAcInfo", "pubinfo", "AcInfo", "Report",
        ]):
            resps.append((r.status, ct, r.url))

    def attach(p):
        p.on("request", on_req)
        p.on("response", on_resp)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 Chrome/120 Safari/537.36",
            locale="ko-KR",
        )
        ctx.on("page", attach)
        page = ctx.new_page()
        attach(page)

        try:
            page.goto(LIST_URL, wait_until="networkidle", timeout=60_000)
        except Exception:
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)

        # 클릭 전 buffer 클리어
        reqs.clear()
        resps.clear()

        sel = f"[onclick*=\"fn_RdViewer('{pid}','{YEAR}')\"]"
        btn = page.locator(sel)
        n = btn.count()
        print(f"  selector matches: {n}")
        if n == 0:
            browser.close()
            return

        popup = None
        try:
            with ctx.expect_page(timeout=15_000) as pi:
                btn.first.click()
            popup = pi.value
            attach(popup)
            popup_urls.append(("after_click", popup.url))
            print(f"  popup url(after_click): {popup.url!r}")
            try:
                popup.wait_for_load_state("networkidle", timeout=30_000)
                popup_urls.append(("networkidle", popup.url))
            except Exception as e:
                print(f"  networkidle timeout: {str(e)[:80]}")
            print(f"  popup url(final): {popup.url!r}")
        except Exception as e:
            print(f"  popup expect fail: {str(e)[:120]}")

        time.sleep(6)
        # popup의 현재 URL 한 번 더
        if popup:
            try:
                print(f"  popup url(after sleep): {popup.url!r}")
            except Exception:
                pass

        browser.close()

    print(f"\n  -- requests after click ({len(reqs)}) --")
    for m, u, t in reqs[:20]:
        print(f"    {m:5s} [{t:10s}] {u}")
    print(f"\n  -- responses after click ({len(resps)}) --")
    for s, ct, u in resps[:20]:
        print(f"    {s} {ct:40s} {u}")


def main():
    diagnose("9")
    diagnose("46")


if __name__ == "__main__":
    main()
