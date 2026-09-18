@echo off
setlocal
cd /d "%~dp0"
title Portal de Seguimiento V9

echo Iniciando Portal de Seguimiento V9...
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 server.py --open
  if %errorlevel%==0 goto :end
  echo.
  echo El iniciador "py" no pudo arrancar Python 3. Probando "python"...
)

where python >nul 2>&1
if %errorlevel%==0 (
  python server.py --open
  goto :end
)

echo.
echo ERROR: No se pudo iniciar Python 3.
echo Instala Python 3 desde https://www.python.org/downloads/ y marca "Add Python to PATH".
echo.
pause

:end
endlocal
