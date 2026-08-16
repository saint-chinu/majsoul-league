@echo off
rem ==== 初回セットアップ（ダブルクリックするだけ） ====
rem 1. リポジトリを最新化
rem 2. タスクスケジューラに毎日5:00の自動更新を登録
rem 3. お試しで1回実行（この画面で動きを確認できる）
rem git pull で実行中の自分自身が書き換わると誤動作するため、
rem 一時フォルダへコピーしてから本体を実行する。
if "%~1"=="__copied" goto main
copy /y "%~f0" "%TEMP%\majsoul_setup_run.bat" >nul
call "%TEMP%\majsoul_setup_run.bat" __copied "%~dp0"
exit /b %errorlevel%

:main
cd /d "%~2"

echo ============================================
echo  1/3  リポジトリを最新化します
echo ============================================
set "GIT=git"
where git >nul 2>&1
if errorlevel 1 set "GIT=C:\Users\pgzdv\AppData\Local\GitHubDesktop\app-3.5.9\resources\app\git\cmd\git.exe"
"%GIT%" pull --ff-only origin main
if errorlevel 1 (
  echo 最新化に失敗しました。GitHub Desktop で「Pull origin」してから、もう一度このファイルを実行してください。
  pause
  exit /b 1
)

echo.
echo ============================================
echo  2/3  タスクスケジューラに登録します（毎日 5:00）
echo ============================================
schtasks /Create /TN "MajsoulLeagueAutoUpdate" /TR "\"%~2run_auto.bat\"" /SC DAILY /ST 05:00 /F
if errorlevel 1 (
  echo 登録に失敗しました。あとで AUTO_UPDATE.md の手順で手動登録してください。
) else (
  echo 登録OK: 毎日 5:00、PCにログオンしているときだけ自動で走ります。
  echo 時刻を変えたい場合は「タスクスケジューラ」で MajsoulLeagueAutoUpdate を編集。
)

echo.
echo ============================================
echo  3/3  お試しで1回実行します（数分かかります）
echo ============================================
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run_auto_update.py
) else (
  py run_auto_update.py
)
if errorlevel 1 (
  echo.
  echo ※ エラーで止まりました。画面に LOGIN_EXPIRED と出ている場合は、
  echo    いつも通り一度手動で管理画面にログインしてから再実行してください。
  echo    それ以外はこの画面の内容を貼って相談してください。データは消えていません。
) else (
  echo.
  echo 全部成功しました。明日からは毎日 5:00 に自動で更新されます。
)
echo.
pause
