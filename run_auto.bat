@echo off
rem 完全自動更新（タスクスケジューラ登録用）。ログは logs\ に日付別で残す。
cd /d "%~dp0"
if not exist logs mkdir logs
set LOGFILE=logs\auto_%date:~0,4%%date:~5,2%%date:~8,2%.log
py run_auto_update.py >> "%LOGFILE%" 2>&1
