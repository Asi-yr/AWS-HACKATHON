@echo off
start cmd /k "cd /d %~dp0 && .venv\Scripts\activate && python main.py"
start cmd /k "cd /d %~dp0ligtas_app && flutter run -d chrome"