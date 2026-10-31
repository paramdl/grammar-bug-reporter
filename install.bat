@echo off
echo Installing Grammar Tool dependencies...
echo.
py -m pip install -r requirements.txt
echo.
echo Done! Run the app with:
echo   py main.py
echo.
echo To auto-start with Windows, create a shortcut to main.py in:
echo   shell:startup
pause
