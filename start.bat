@echo off
rem Dada Academy: one command to run the whole app on this laptop (offline mode needs no key, no internet).
rem Python choice: DADA_PYTHON (explicit override, used by the check scripts), else runtime\python\python.exe
rem (bundled), else .venv (created with py -3.13 and requirements.txt only if missing).
rem Automation: NOPAUSE=1 skips every pause, NOBROWSER=1 skips opening the browser.
rem To stop: close the "Dada Academy server" window.
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
title Dada Academy
echo.
echo ==== Dada Academy ====
set "PYTHONNOUSERSITE=1"
set "VPY="

if defined DADA_PYTHON (
  set "VPY=%DADA_PYTHON%"
  echo Python: DADA_PYTHON override
  goto :have_python
)
if exist "%ROOT%\runtime\python\python.exe" (
  set "VPY=%ROOT%\runtime\python\python.exe"
  echo Python: bundled, in runtime\python
  goto :have_python
)
if exist "%ROOT%\.venv\Scripts\python.exe" (
  set "VPY=%ROOT%\.venv\Scripts\python.exe"
  echo Python: .venv
  goto :have_python
)

echo No bundled Python and no .venv: creating .venv with Python 3.13, one time...
py -3.13 -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo Python 3.13 was not found.
  echo Install it from https://www.python.org/downloads/ or run:
  echo     winget install -e --id Python.Python.3.13 --scope user
  echo then run start.bat again.
  goto :fail
)
py -3.13 -m venv "%ROOT%\.venv" || goto :fail
set "VPY=%ROOT%\.venv\Scripts\python.exe"
echo Installing packages, a few minutes the first time...
"%VPY%" -m pip install --disable-pip-version-check -q -r "%ROOT%\requirements.txt" || goto :fail

:have_python
"%VPY%" -c "import onnxruntime" >nul 2>&1
if errorlevel 1 (
  echo onnxruntime could not be loaded. This usually means the Microsoft Visual C++ runtime is missing.
  echo Install it from https://aka.ms/vs/17/release/vc_redist.x64.exe or run:
  echo     winget install -e --id Microsoft.VCRedist.2015+.x64
  echo then run start.bat again.
  goto :fail
)

rem ---- port: 8000, else 8010 when 8000 is busy ----
set "PORT=8000"
"%VPY%" -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(1 if s.connect_ex(('127.0.0.1',8000))==0 else 0)" >nul 2>&1
if errorlevel 1 (
  set "PORT=8010"
  echo Port 8000 is busy, using 8010.
)

echo Starting the server on http://127.0.0.1:%PORT% ...
start "Dada Academy server" /MIN /D "%ROOT%" "%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --log-level warning

echo Waiting for the server to be ready, up to 60 seconds...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/api/health' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){ $ok=$true; break } } catch { Start-Sleep 1 } }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
  echo The server did not answer in 60 seconds. Look at the "Dada Academy server" window for the error.
  goto :fail
)

if not "%NOBROWSER%"=="1" start "" "http://127.0.0.1:%PORT%/"
echo.
echo ==== Dada Academy is running at http://127.0.0.1:%PORT%/ ====
echo To stop: close the "Dada Academy server" window.
if not "%NOPAUSE%"=="1" pause
exit /b 0

:fail
echo.
echo Something went wrong. Take a screenshot of this window and send it back.
if not "%NOPAUSE%"=="1" pause
exit /b 1
