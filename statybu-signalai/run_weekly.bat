@echo off
rem Savaitinis statybu signalu paleidimas (Windows uzduociu planuoklei).
rem Planuoklyje nurodykite si faila; darbinis aplankas nustatomas automatiskai.
rem Zurnalas: isvestis\paleidimai.log. Isejimo kodas 2 - bent viena salis nepasiekta.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist isvestis mkdir isvestis
set "PY=python"
where py >/dev/null 2>/dev/null && set "PY=py -3"
echo ==== %date% %time% >> "isvestis\paleidimai.log"
%PY% sistema.py run >> "isvestis\paleidimai.log" 2>&1
set "KODAS=%errorlevel%"
if not "%KODAS%"=="0" echo KLAIDA: sistema.py run baige darba su kodu %KODAS% >> "isvestis\paleidimai.log"
endlocal & exit /b %KODAS%
