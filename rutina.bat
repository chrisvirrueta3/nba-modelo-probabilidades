@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
set AUTO=0
if /i "%~1"=="auto" set AUTO=1
set PY=..\.venv\Scripts\python.exe
if not exist "%PY%" (
  echo No encuentro el entorno de Python en ..\.venv
  echo Crea el entorno primero: python -m venv ..\.venv
  if "%AUTO%"=="0" pause
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
call :paso "6b  Modelo de spreads y totales"   src\puntos.py                      || goto error
call :paso "7/9 Momios (si son viejos)"       src\descargar_momios.py --si-viejo 90 || goto error
call :paso "8/9 Valor y apuestas simuladas"   src\valor.py                       || goto error
call :paso "9/9 Liquidando y exportando web"  src\liquidar.py                    || goto error
"%PY%" src\exportar_web.py || goto error

echo.
echo --- Publicando en GitHub Pages ---
if not exist .git (
  echo Esta carpeta no esta conectada a GitHub: corre configurar_github.bat una vez.
  goto fin
)
git add -A
git diff --cached --quiet || git commit -q -m "Actualizacion diaria %date%"
git pull -q --rebase --autostash -X theirs || goto error_git
git push -q || goto error_git
echo Subido. La pagina se actualiza en 1-2 minutos.
"%PY%" src\avisar.py

:fin
echo.
echo ============================================
echo   LISTO. Pagina: chrisvirrueta3.github.io/nba-modelo-probabilidades
echo ============================================
if "%AUTO%"=="0" start "" "https://chrisvirrueta3.github.io/nba-modelo-probabilidades"
if "%AUTO%"=="0" pause
exit /b 0

:error_git
echo.
echo *** No se pudo subir a GitHub. Los datos SI se calcularon; solo falta publicarlos. ***
echo *** Copia el error de arriba y pegaselo a Claude. ***
if "%AUTO%"=="1" "%PY%" src\avisar.py --error
if "%AUTO%"=="0" pause
exit /b 1

:paso
echo.
echo --- %~1 ---
"%PY%" %2 %3 %4
exit /b %errorlevel%

:error
echo.
echo *** Algo fallo en el paso anterior. Copia el error de arriba y pegaselo a Claude. ***
if "%AUTO%"=="1" "%PY%" src\avisar.py --error
if "%AUTO%"=="0" pause
exit /b 1
