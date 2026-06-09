@echo off
REM 학과 졸업요건 corpus 보강 — 10개 학과 풀세트 (로컬 실행)
REM 사용: run_dept_grad_10.bat [discover^|crawl^|all]
setlocal
cd /d "%~dp0..\.."

set LIST=scripts\sprint2\dept_list_10.json
set OUT_DIR=data\sprint3\dept_grad_10
set CAND=%OUT_DIR%\candidates.jsonl
set CHUNKS=%OUT_DIR%\chunks_raw.jsonl

if not exist %OUT_DIR% mkdir %OUT_DIR%

set MODE=%1
if "%MODE%"=="" set MODE=all

if /I "%MODE%"=="discover" goto :discover
if /I "%MODE%"=="all" goto :discover
goto :crawl_only

:discover
echo === [1/2] discover ===
python -m scripts.sprint2.dept_grad discover --dept-list %LIST% --out %CAND%
if errorlevel 1 exit /b 1
if /I "%MODE%"=="discover" goto :end

:crawl_only
:crawl
echo === [2/2] crawl ===
python -m scripts.sprint2.dept_grad crawl --candidates %CAND% --out %CHUNKS% --top-n 3

:end
echo.
echo OK. Done. Upload %CHUNKS% to workspace.
endlocal
