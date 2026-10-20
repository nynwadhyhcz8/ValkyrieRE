@echo off
setlocal
set PYTHONUTF8=1
python "%~dp0valkyrie.py" %*
endlocal
