@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   PROGRAMAR RUTINA AUTOMATICA
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0programar_rutina.ps1"
if errorlevel 1 (
  echo.
  echo *** No se pudo programar. Copia el error de arriba y pegaselo a Claude. ***
  pause
  exit /b 1
)
echo.
echo Listo: rutina.bat va a correr solo todos los dias a las 12:00 y a las 17:30.
echo La computadora tiene que estar prendida (si estaba apagada, corre al prenderla).
echo Si algo falla te llega un aviso al telefono (ntfy) y el detalle queda en datos\ultima_rutina.log
echo.
echo Para quitarlo: corre quitar_rutina.bat
pause
