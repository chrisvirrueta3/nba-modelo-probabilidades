@echo off
chcp 65001 >nul
schtasks /Delete /F /TN "NBA rutina mediodia"
schtasks /Delete /F /TN "NBA rutina tarde"
echo Listo: rutina.bat ya no corre solo.
pause
