@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   CONECTAR ESTA CARPETA CON GITHUB (una sola vez)
echo ============================================
where git >nul 2>nul || (
  echo No encuentro Git. Instalalo desde https://git-scm.com y vuelve a intentar.
  pause
  exit /b 1
)
if exist .git (
  echo Esta carpeta ya esta conectada a GitHub.
  git status -sb
  pause
  exit /b 0
)
git init -q -b main || goto error
git remote add origin https://github.com/chrisvirrueta3/nba-modelo-probabilidades.git || goto error
git config user.name "Christopher Virrueta"
git config user.email "chrisvirrueta3@users.noreply.github.com"
echo.
echo Descargando el historial de GitHub...
echo (si se abre una ventana para iniciar sesion en GitHub, aceptala)
git fetch -q origin main || goto error
git reset -q --mixed origin/main || goto error
git branch -q --set-upstream-to=origin/main main
echo.
echo Diferencias entre tu carpeta y GitHub (deberian ser solo datos o nada):
git status -s
echo.
echo LISTO. Desde ahora rutina.bat sube los datos y la pagina se actualiza sola:
echo https://chrisvirrueta3.github.io/nba-modelo-probabilidades
pause
exit /b 0

:error
echo.
echo *** Algo fallo. Copia el error de arriba y pegaselo a Claude. ***
pause
exit /b 1
