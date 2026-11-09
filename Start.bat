@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Bitte zuerst die Python-Umgebung einrichten ^(siehe README.md^).
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
