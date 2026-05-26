@echo off
REM Sprint 1 master runner (Windows).
REM
REM Usage:
REM   scripts\run_sprint1.bat              :: full pipeline
REM   scripts\run_sprint1.bat day1         :: Day 1 only
REM   scripts\run_sprint1.bat verify-only  :: verify only
REM   scripts\run_sprint1.bat attachments  :: process attachments for day1,2,4

setlocal EnableDelayedExpansion
cd /d "%~dp0\.."

set "DAY=%~1"
if "!DAY!"=="" set "DAY=all"

if /I "!DAY!"=="verify-only" (
    python -m scripts.sprint1.verify
    exit /b %ERRORLEVEL%
)

if /I "!DAY!"=="attachments" (
    for %%d in (day1 day2 day4) do (
        echo === %%d attachments ===
        python -m scripts.sprint1.process_attachments %%d --hwp-prefer hwp5txt --max 80
    )
    python -m scripts.sprint1.verify
    exit /b %ERRORLEVEL%
)

echo === 0. pre-inspect ===
python -m scripts.sprint1.pre_inspect

if /I "!DAY!"=="all" (
    for %%d in (day1 day2 day3 day4 day5) do (
        echo.
        echo === %%d ===
        python -m scripts.sprint1.runner %%d
    )
    echo.
    echo === attachments (day1, day2, day4) ===
    for %%d in (day1 day2 day4) do (
        python -m scripts.sprint1.process_attachments %%d --hwp-prefer hwp5txt --max 80
    )
) else (
    echo === !DAY! ===
    python -m scripts.sprint1.runner !DAY!
    if /I "!DAY!"=="day1" (
        python -m scripts.sprint1.process_attachments day1 --hwp-prefer hwp5txt --max 50
    )
    if /I "!DAY!"=="day2" (
        python -m scripts.sprint1.process_attachments day2 --hwp-prefer hwp5txt --max 100
    )
    if /I "!DAY!"=="day4" (
        python -m scripts.sprint1.process_attachments day4 --hwp-prefer hwp5txt --max 30
    )
)

echo.
echo === verify ===
python -m scripts.sprint1.verify

endlocal
