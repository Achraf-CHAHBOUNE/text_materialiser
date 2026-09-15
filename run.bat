@echo off
REM ==================================================================
REM  Anonymize one client folder, then rebuild results\ for the client.
REM
REM    run.bat 01_civile                 everything left to do
REM    run.bat 01_civile --limit 500     only the next 500
REM    run.bat 01_civile --sample 200    a random 200, as a test
REM
REM  The folder must sit in data\corpus\. Safe to stop and run again:
REM  finished rulings are skipped and nothing is paid for twice.
REM ==================================================================
setlocal
if "%~1"=="" (
  echo Usage: run.bat FOLDER [options]    -- folders in data\corpus:
  dir /b /ad "%~dp0data\corpus"
  exit /b 1
)
set "NAME=%~1"
shift
cd /d "%~dp0pipeline"
set "PYTHONUTF8=1"
set "STATE_FILE=../data/work/%NAME%/.state.json"
set "DB_PATH=../data/work/cases.db"

python -m anonymizer --input "../data/corpus/%NAME%" --output "../data/work/%NAME%" --corpus %NAME% --workers 16 --budget 15 %1 %2 %3 %4 %5 %6
python -m anonymizer.assemble --work ../data/work --out ../results

echo.
echo  Done. The client hand-off is in the results folder.
pause
