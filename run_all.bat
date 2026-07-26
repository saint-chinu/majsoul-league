@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run_all.py
) else (
  py run_all.py
)
echo.
echo 終了しました。Enterで閉じます。
pause >nul
