@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo 未找到 Python，请先安装 Python 3.10 以上版本 & pause & exit /b 1)
python -c "import webview" 2>nul || python -m pip install -q pywebview
start "" pythonw app.py
