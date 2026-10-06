@echo off
rem Savaitinis statybu signalu paleidimas (Windows uzduociu planuoklei).
rem Planuoklyje nurodykite si faila; darbinis aplankas nustatomas automatiskai.
rem Zurnalas: isvestis\paleidimai.log. Isejimo kodas 2 - bent viena salis nepasiekta, 3 - nerastas Python.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist isvestis mkdir isvestis
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% --version >nul 2>nul || (echo KLAIDA: nerastas Python 3.10+ ^(python.org^) >> "isvestis\paleidimai.log" & endlocal & exit /b 3)
echo ==== %date% %time% >> "isvestis\paleidimai.log"
%PY% sistema.py run >> "isvestis\paleidimai.log" 2>&1
set "KODAS=%errorlevel%"
if not "%KODAS%"=="0" echo KLAIDA: sistema.py run baige darba su kodu %KODAS% >> "isvestis\paleidimai.log"
endlocal & exit /b %KODAS%
