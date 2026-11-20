@echo off
chcp 65001 >nul
schtasks /Delete /F /TN "NBA rutina mediodia"
schtasks /Delete /F /TN "NBA rutina tarde"
schtasks /Delete /F /TN "NBA revisar lesiones"
echo Listo: rutina.bat ya no corre solo.
pause
