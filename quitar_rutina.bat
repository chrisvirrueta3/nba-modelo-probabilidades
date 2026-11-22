@echo off
chcp 65001 >nul
schtasks /Delete /F /TN "NBA rutina mediodia" 2>nul
schtasks /Delete /F /TN "NBA rutina manana"
schtasks /Delete /F /TN "NBA resumen semanal"
schtasks /Delete /F /TN "NBA rutina tarde"
schtasks /Delete /F /TN "NBA rutina al prender"
schtasks /Delete /F /TN "NBA revisar lesiones"
echo Listo: rutina.bat ya no corre solo.
pause
