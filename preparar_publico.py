"""Arma dist/ con UN solo index.html cifrado (StatiCrypt) que incluye solo publico.js. No sube nada.

Lo que se publica es solo texto cifrado: sin la clave (clave.txt, nunca se publica) no se lee nada.
Si algo falla, dist/ queda vacio y publicar.bat se cancela.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

r = Path(__file__).resolve().parent
build = r / "_build"
d = r / "dist"
for p in (build, d):
    shutil.rmtree(p, ignore_errors=True)
build.mkdir()
d.mkdir()


# App instalable (PWA). El manifiesto y el registro del service worker se inyectan DOS veces:
# en la pagina antes de cifrar (StatiCrypt la reescribe con document.write al descifrar y borra el
# <head> de la envoltura) y en la envoltura cifrada (para que Chrome la reconozca desde el inicio).
PWA_ARCHIVOS = ["manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png", "icon-maskable-512.png"]
PWA_HEAD = (
    '<link rel="manifest" href="manifest.webmanifest">'
    '<meta name="theme-color" content="#2B4C9B">'
    '<link rel="apple-touch-icon" href="icon-192.png">'
    '<script>if("serviceWorker"in navigator&&(location.protocol==="https:"||location.hostname==="localhost")){'
    'var r=function(){navigator.serviceWorker.register("sw.js").catch(function(){})};'
    'document.readyState==="complete"?r():addEventListener("load",r)}</script>'
)


def con_pwa(html):
    if "</head>" not in html:
        sys.exit("ERROR: no hay </head> donde inyectar el manifiesto.")
    return html.replace("</head>", PWA_HEAD + "</head>", 1)


def inline(m):
    codigo = (r / "data" / m.group(1)).read_text(encoding="utf-8")
    return "<script>\n" + codigo.replace("</", "<\\/") + "\n</script>"


html = (r / "index.html").read_text(encoding="utf-8")
html, privados = re.subn(r'<script src="data/privado\.js"(?: onerror="void 0")?></script>', "", html)
html, n = re.subn(r'<script src="data/(publico\.js)"></script>', inline, html)
if n != 1 or privados != 1 or 'src="data/' in html:
    sys.exit("ERROR: no se pudo incrustar publico.js y retirar la etiqueta de privado.js del HTML.")
(build / "index.html").write_text(con_pwa(html), encoding="utf-8")

archivo_clave = r / "clave.txt"
clave = (archivo_clave.read_text(encoding="ascii") if archivo_clave.exists()
         else os.environ.get("TABLERO_CLAVE", "")).strip()
if len(clave) < 8:
    sys.exit("ERROR: falta clave.txt o TABLERO_CLAVE, o la clave tiene menos de 8 caracteres.")

npx = shutil.which("npx.cmd") or shutil.which("npx")
if not npx:
    sys.exit("ERROR: no se encontro npx. Instala Node.js.")
# Rutas relativas a r: staticrypt las vuelve a unir con el directorio actual.
cmd = [npx, "--yes", "staticrypt@3.5.4", "_build/index.html", "-d", "dist",
       "--config", ".staticrypt.json", "--short",
       "--template-title", "Tablero", "--template-instructions", "Escribe la clave para entrar.",
       "--template-placeholder", "Clave", "--template-button", "Entrar",
       "--template-remember", "Recordarme en este dispositivo",
       "--template-error", "Clave incorrecta.", "--template-color-primary", "#0f6b66",
       "--template-color-secondary", "#eef1f3"]
env = dict(os.environ, STATICRYPT_PASSWORD=clave)
res = subprocess.run(cmd, cwd=r, env=env)
shutil.rmtree(build, ignore_errors=True)
if res.returncode != 0:
    shutil.rmtree(d, ignore_errors=True)
    sys.exit("ERROR: fallo el cifrado.")

salida = (d / "index.html").read_text(encoding="utf-8")
# Marcas que SOLO existen en claro: si aparecen, el cifrado no se aplico.
for marca in ("window.PRIVADO", "Tienda Etsy", "Hola, Diego", "TableroDiego", "Gmail", "pendientes_fecha"):
    if marca in salida:
        shutil.rmtree(d, ignore_errors=True)
        sys.exit("ERROR: dist contiene texto en claro (%s). Publicacion cancelada." % marca)
(d / "index.html").write_text(con_pwa(salida), encoding="utf-8")
for nombre in PWA_ARCHIVOS:
    shutil.copy2(r / "pwa" / nombre, d / nombre)
extra = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())
if extra != sorted(["index.html"] + PWA_ARCHIVOS):
    shutil.rmtree(d, ignore_errors=True)
    sys.exit("ERROR: dist debe tener index.html y los archivos de la app, tiene %s." % extra)
print("dist/ listo (cifrado):", extra)
