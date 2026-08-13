@echo off
REM Refresh the committed web snapshot from the local Zara DB, then push it.
REM Pushing to GitHub triggers the "Refresh Zara Polyamide Index" Action, which
REM rebuilds the dashboard with live FX and republishes it to GitHub Pages.
REM
REM Run this on the PC that has the Zara parser, AFTER the weekly scrape (the
REM prices only change weekly). The cloud refreshes FX daily on its own.
REM   web_update.bat
setlocal
pushd "%~dp0"

echo [web_update] exporting snapshot from the local DB...
python export_snapshot.py
if errorlevel 1 ( echo [web_update] export failed & popd & exit /b 1 )

git add web\snapshot_local.json
git diff --cached --quiet
if %ERRORLEVEL%==0 (
  echo [web_update] snapshot unchanged - nothing to push.
  popd & exit /b 0
)

for /f "tokens=1-3 delims=/ " %%a in ("%DATE%") do set "TODAY=%%c-%%b-%%a"
git commit -m "chore: refresh Zara price snapshot (%TODAY%)"
git push
if errorlevel 1 ( echo [web_update] push failed - check 'git remote' and credentials & popd & exit /b 1 )

echo [web_update] pushed - the GitHub Action will rebuild and republish shortly.
popd
endlocal
