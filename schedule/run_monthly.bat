@echo off
REM Wrapper the Windows scheduled task calls on the 20th of every month.
REM Sets the working dir to the project root, runs the pipeline, tees output to a log.
setlocal
REM project root = parent of this schedule\ folder
pushd "%~dp0\.."
set "PI_ROOT=%CD%"
if not exist "%PI_ROOT%\logs" mkdir "%PI_ROOT%\logs"
set "STAMP=%DATE:/=-%_%TIME::=-%"
set "LOG=%PI_ROOT%\logs\task_%STAMP: =0%.log"

where python >nul 2>nul
if errorlevel 1 (
  echo [task] python not found on PATH>>"%LOG%"
  popd & exit /b 9
)

echo [task] %DATE% %TIME% starting Polyamide Index monthly run>>"%LOG%"
python "%PI_ROOT%\run_monthly.py" %* 1>>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo [task] finished rc=%RC%>>"%LOG%"
popd
endlocal & exit /b %RC%
