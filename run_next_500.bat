@echo off
REM ============================================================
REM  Anonymize the NEXT 500 documents of 02_statut_personnel.
REM  Safe to run again and again - already-finished files are
REM  skipped automatically. NEVER delete the output_first folder.
REM ============================================================
setlocal
cd /d "%~dp0pipeline"
set "PYTHONUTF8=1"
set "STATE_FILE=../output_first/.state.json"
set "DB_PATH=../output_first/cases.db"

python -m anonymizer --input "../02_statut_personnel" --output "../output_first" --workers 32 --budget 10 --limit 500

echo.
echo ============================================================
echo  Chunk finished. Run this file AGAIN for the next 500.
echo  When it says "0 to process", everything is complete.
echo ============================================================
pause
