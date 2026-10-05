@echo off
title LUAR
rem Windows launcher: double-click to open LUAR in your browser (http://127.0.0.1:7860).
rem Keep this window open while you use LUAR; close it to stop LUAR.
rem Extra options are passed on, e.g.  LUAR.bat --port 7861 --no-browser
cd /d "%USERPROFILE%"
echo Opening LUAR... your browser opens in a few seconds.
echo To stop LUAR, close this window.
echo.
python -m luar ui %*
if errorlevel 1 (
  echo.
  echo LUAR could not start. See the message above.
  echo If it says "No module named luar", install it first:  pip install "luar[all]"
  pause
)
