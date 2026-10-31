@echo off
REM Launch GrammarTool silently in the background (no console window).
cd /d "%~dp0"
start "" pythonw main.py
exit
