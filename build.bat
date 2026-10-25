@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -q pyinstaller pywebview
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name AICacheCleaner --icon assets\icon.ico ^
  --add-data "web;web" ^
  app.py
echo.
echo 打包完成：dist\AICacheCleaner.exe
pause
