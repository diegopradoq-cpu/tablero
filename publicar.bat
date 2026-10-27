@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 (
  echo ERROR: no se pudo abrir la carpeta del tablero.
  exit /b 1
)

python -I actualizar.py
if errorlevel 1 (
  echo ERROR: fallo actualizar.py. No se publico el tablero.
  exit /b 1
)

python -I preparar_publico.py
if errorlevel 1 (
  echo ERROR: fallo preparar_publico.py. No se publico el tablero.
  exit /b 1
)
if exist "dist\data" (
  echo ERROR: dist contiene una carpeta data en claro. Publicacion cancelada.
  exit /b 1
)
if not exist "dist\index.html" (
  echo ERROR: falta dist\index.html. Publicacion cancelada.
  exit /b 1
)
findstr /C:"staticrypt" "dist\index.html" >nul
if errorlevel 1 (
  echo ERROR: dist\index.html no esta cifrado. Publicacion cancelada.
  exit /b 1
)

where netlify >nul 2>nul
if not errorlevel 1 (
  call netlify deploy --prod --dir=dist --no-build
) else (
  where npx >nul 2>nul
  if errorlevel 1 (
    echo ERROR: no se encontro Netlify ni npx. Instala Node.js y vuelve a intentar.
    exit /b 1
  )
  call npx --yes netlify-cli deploy --prod --dir=dist --no-build
)
if errorlevel 1 (
  echo ERROR: fallo el deploy de Netlify. Revisa conexion, login y sitio vinculado.
  exit /b 1
)
echo OK: tablero publicado en Netlify.
exit /b 0
