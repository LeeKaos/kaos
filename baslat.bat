@echo off
REM ==========================================================================
REM  WioForge - Baslatici (Windows)
REM  Bu betik Python'u bulur ve WioForge menusunu acar.
REM  Kullanim:  baslat.bat
REM ==========================================================================
setlocal
cd /d "%~dp0"

set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" ( where py >nul 2>nul && set PY=py )
if "%PY%"=="" ( where python3 >nul 2>nul && set PY=python3 )

if "%PY%"=="" (
  echo [HATA] Python bulunamadi. Lutfen Python 3.8+ kurun: https://www.python.org/downloads/
  echo Kurulumda "Add Python to PATH" secenegini isaretleyin.
  pause
  exit /b 1
)

echo WioForge baslatiliyor (%PY%)...
"%PY%" wioforge.py %*

endlocal
pause
