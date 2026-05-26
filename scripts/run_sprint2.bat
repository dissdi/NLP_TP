@echo off
REM Sprint 2 master runner (Windows). ASCII-only + CRLF.
REM
REM Usage:
REM   scripts\run_sprint2.bat              :: full pipeline
REM   scripts\run_sprint2.bat inspect      :: spike only (rule, dept, alimi)
REM   scripts\run_sprint2.bat day1         :: Day 1 (RULE_HWP + PDF)
REM   scripts\run_sprint2.bat day2         :: Day 2
REM   scripts\run_sprint2.bat day3         :: Day 3 + cross_tag/faq_seed/dorm_js
REM   scripts\run_sprint2.bat attachments  :: process attachments day1..day3
REM   scripts\run_sprint2.bat dept-discover :: dept_grad discover only (inspect first)
REM   scripts\run_sprint2.bat dept-crawl    :: dept_grad crawl only (after discover)
REM   scripts\run_sprint2.bat dept-grad    :: dept_grad discover + crawl
REM   scripts\run_sprint2.bat alimi        :: alimi spike only
REM   scripts\run_sprint2.bat verify       :: verify only

setlocal EnableDelayedExpansion
cd /d "%~dp0\.."

set "DAY=%~1"
if "!DAY!"=="" set "DAY=all"

if /I "!DAY!"=="verify" (
    python -m scripts.sprint2.verify
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="inspect" (
    echo === inspect: rule list ===
    python -m crawler.adapters.e_rule_hwp inspect "https://plus.cnu.ac.kr/_prog/rule/?site_dvs_cd=kr&menu_dvs_cd=0703"
    echo.
    echo === inspect: alimi spike ===
    python -m scripts.sprint2.dstat spike-alimi
    echo.
    echo === inspect: dept grad discover ===
    python -m scripts.sprint2.dept_grad discover --dept-list scripts/sprint2_dept_list.json
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="dept-discover" (
    python -m scripts.sprint2.dept_grad discover --dept-list scripts/sprint2_dept_list.json
    echo.
    echo Inspect: data\sprint2\day1\dept_grad_candidates.jsonl
    echo Next:    scripts\run_sprint2.bat dept-crawl
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="dept-crawl" (
    python -m scripts.sprint2.dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="dept-grad" (
    python -m scripts.sprint2.dept_grad discover --dept-list scripts/sprint2_dept_list.json
    python -m scripts.sprint2.dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="alimi" (
    python -m scripts.sprint2.dstat spike-alimi
    echo.
    echo NOTE: If PDF URL found, then:
    echo   python -m scripts.sprint2.dstat fetch-pdf "URL"
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="attachments" (
    for %%d in (day1 day2 day3) do (
        echo === %%d attachments ===
        python -m scripts.sprint2.process_attachments %%d --hwp-prefer hwp5txt --max 80
    )
    python -m scripts.sprint2.verify
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="all" (
    echo === 0. inspect ===
    python -m crawler.adapters.e_rule_hwp inspect "https://plus.cnu.ac.kr/_prog/rule/?site_dvs_cd=kr&menu_dvs_cd=0703"
    python -m scripts.sprint2.dstat spike-alimi
    python -m scripts.sprint2.dept_grad discover --dept-list scripts/sprint2_dept_list.json

    for %%d in (day1 day2 day3) do (
        echo.
        echo === %%d main runner ===
        python -m scripts.sprint2.runner %%d
    )

    echo.
    echo === day1 dept_grad crawl ===
    python -m scripts.sprint2.dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl

    echo.
    echo === day3 cross_tag / faq_seed / dorm_js ===
    python -m scripts.sprint2.cross_tag
    python -m scripts.sprint2.faq_seed
    python -m scripts.sprint2.dorm_js

    echo.
    echo === attachments day1..day3 ===
    for %%d in (day1 day2 day3) do (
        python -m scripts.sprint2.process_attachments %%d --hwp-prefer hwp5txt --max 80
    )
) else (
    echo === !DAY! main runner ===
    python -m scripts.sprint2.runner !DAY!
    if /I "!DAY!"=="day1" (
        python -m scripts.sprint2.dept_gra