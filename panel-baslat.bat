@echo off
REM ==========================================================================
REM  WioForge - Web Panel Baslatici (Python, Windows)
REM  Tarayicida http://localhost:8080 adresini acar.
REM  Kullanim:  panel-baslat.bat [port]
REM ==========================================================================
setlocal
cd /d "%~dp0"

set PORT=%1
if "%PORT%"=="" set PORT=8080

set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" ( where py >nul 2>nul && set PY=py )
if "%PY%"=="" ( where python3 >nul 2>nul && set PY=python3 )

if "%PY%"=="" (
  echo [HATA] Python bulunamadi. Lutfen Python 3.8+ kurun.
  pause
  exit /b 1
)

echo WioForge Web Paneli baslatiliyor: http://localhost:%PORT%
"%PY%" wioforge.py panel --port %PORT%

endlocal
pause
