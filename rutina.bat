@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
set PY=..\.venv\Scripts\python.exe
if not exist "%PY%" (
  echo No encuentro el entorno de Python en ..\.venv
  echo Crea el entorno primero: python -m venv ..\.venv
  pause
  exit /b 1
)

echo ============================================
echo   RUTINA DIARIA - NBA PROBABILIDADES
echo ============================================

call :paso "1/9 Actualizando partidos"        src\descargar_partidos.py --actual || goto error
call :paso "2/9 Limpiando partidos"           src\limpiar_partidos.py            || goto error
call :paso "3/9 Actualizando jugadores"       src\descargar_jugadores.py --actual || goto error
call :paso "4/9 Calculando bajas"             src\bajas.py                       || goto error
call :paso "5/9 Recalculando Elo"             src\elo.py                         || goto error
call :paso "6/9 Reentrenando modelo"          src\modelo.py                      || goto error
call :paso "7/9 Momios (si son viejos)"       src\descargar_momios.py --si-viejo 240 || goto error
call :paso "8/9 Valor y apuestas simuladas"   src\valor.py                       || goto error
call :paso "9/9 Liquidando y exportando web"  src\liquidar.py                    || goto error
"%PY%" src\exportar_web.py || goto error

echo.
echo ============================================
echo   LISTO. Para actualizar la pagina:
echo   arrastra la carpeta "web" (se abre ahora)
echo   a la pestana Deploys de Netlify.
echo ============================================
start "" explorer "%~dp0web"
start "" "https://app.netlify.com/projects/nba-modelo-probabilidades/deploys"
pause
exit /b 0

:paso
echo.
echo --- %~1 ---
"%PY%" %2 %3 %4
exit /b %errorlevel%

:error
echo.
echo *** Algo fallo en el paso anterior. Copia el error de arriba y pegaselo a Claude. ***
pause
exit /b 1
