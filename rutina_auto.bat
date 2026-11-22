@echo off
rem La corre el Programador de tareas de Windows (ver programar_rutina.bat).
rem Hace lo mismo que rutina.bat, sin pausas, y guarda todo en datos\ultima_rutina.log
rem Con "inicio" (al prender o desbloquear la computadora) solo corre si se perdio la de 9:00 o 17:30.
cd /d "%~dp0"
set PYV=..\.venv\Scripts\python.exe
rem Si ya hay una rutina corriendo, no empezar otra
"%PYV%" src\hace_falta.py --ocupado >nul 2>&1 && exit /b 0
if /i "%~1"=="inicio" (
  "%PYV%" src\hace_falta.py >nul 2>&1 || exit /b 0
)
echo %date% %time% > datos\rutina.lock
call rutina.bat auto > datos\ultima_rutina.log 2>&1
del datos\rutina.lock 2>nul
