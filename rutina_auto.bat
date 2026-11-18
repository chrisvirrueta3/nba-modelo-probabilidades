@echo off
rem La corre el Programador de tareas de Windows (ver programar_rutina.bat).
rem Hace lo mismo que rutina.bat, sin pausas, y guarda todo en datos\ultima_rutina.log
cd /d "%~dp0"
call rutina.bat auto > datos\ultima_rutina.log 2>&1
