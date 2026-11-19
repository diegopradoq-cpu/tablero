# Tablero de Diego
Noticias (IA, tecnología, bolsa, política mundial), mercados, guardados, tareas y pendientes.
- `ABRIR.bat`: actualiza datos (RSS + cotizaciones + resumen con LM Studio) y abre el servidor local.
- `feeds.json`: fuentes y watchlist; editar aquí.
- `data/publico.js` (generado) se publica; `data/privado.js` (Gmail/Calendar/pendientes) NUNCA se publica.
- `preparar_publico.py` arma el HTML público cifrado; GitHub Actions lo publica en GitHub Pages.
- Tareas y guardados viven en localStorage del navegador (no sincronizan entre dispositivos).

## Publicar

La publicación se ejecuta desde GitHub Actions: el workflow actualiza noticias y cotizaciones con `actualizar.py --ia-nube`, genera el HTML cifrado mediante `preparar_publico.py` y publica en GitHub Pages. También puede iniciarse manualmente desde la pestaña Actions. `publicar.bat` es obsoleto y no publica.

Configura el secreto `TABLERO_CLAVE` en Actions; `GEMINI_API_KEY` es opcional para resúmenes en la nube. El contenido publicado es un HTML cifrado con StatiCrypt.

`programar_refresco.ps1` queda obsoleto; no registrar la tarea local.

## Hosting: por qué no Netlify

El plan gratis de Netlify asigna 300 créditos al mes y cada deploy de producción consume 15; seis deploys diarios agotarían el plan. El tablero se aloja en GitHub Pages: en Settings → Pages, elegir Source: GitHub Actions.

## Pendiente de mejora (v1 aprobada como borrador, 22 oct 2026)
- Configurar los secretos para el refresco en GitHub Actions.
- Revisar la vista en teléfono (solo se probó en escritorio).
- Filtrar ruido de MarketWatch/Bolsa; afinar fuentes por tema.
- Llenar Hoy (Gmail + Calendar) pidiéndoselo a Claude; decidir login si va a la web.
- Sincronizar guardados y tareas entre dispositivos (hoy son localStorage).

## Rediseño del 22 oct 2026 (publicado el 22 oct 2026 junto con la ronda 4)
- Referencias: Glance (37k estrellas, AGPL, necesita servidor), Homepage (GPL), Dashy (MIT, pesado). Ninguno se puede copiar a un HTML estático, así que se aplicaron sus principios de legibilidad al HTML propio (encargo en `trabajo/encargo-codex-1-rediseno.md`; respaldo anterior en `trabajo/index.antes.html`).
- Cambios: tarjetas de 3 columnas, una sola tipografía, tema claro/oscuro con botón, barra de pestañas inferior en móvil, resumen IA plegable, aviso si los datos tienen más de 12 h, cinta de mercados con botón Pausar.
- Para publicarlo: ejecutar el workflow de GitHub Actions.
- Aviso visto: el feed de Hacker News falla (URLError).

## Fuentes locales (ronda 4)
- Ejecuta `ABRIR.bat` con Python instalado: actualiza y abre `http://127.0.0.1:8765/index.html`.
- En Noticias, cada tarjeta permite consultar «Fuentes (N)» y usar «+ Fuente» para agregar un RSS.
- «Quitar» pide confirmación en el panel; siempre debe quedar una fuente por tema.
- Esta administración solo aparece con datos privados y dirección local; la web pública sigue estática.
- `file://` y `127.0.0.1:8765` tienen localStorage distintos: tareas y guardados del archivo directo no aparecerán allí.
- El servidor queda en segundo plano; para apagarlo en PowerShell: `Stop-Process -Id (Get-Content .\trabajo\servidor-local.pid)` (en la misma sesión, antes de reutilizar ese PID).
- Alternativa visible: ejecuta `python -I servidor_local.py` y apágalo con Ctrl+C; registros del lanzador en `trabajo/servidor-local*.log`.

## Tablero privado (22 oct 2026; sustituido por el cambio del 26 oct)
- preparar_publico.py junta index.html + publico.js en UN solo HTML (privado.js ya no se incrusta) y lo cifra con StatiCrypt (clave en clave.txt, local, nunca se publica; .staticrypt.json guarda la sal para que 'Recordarme' siga valiendo tras cada publicación).
- publicar.bat se cancela si dist/ tiene algo en claro. La web pide la clave al abrir.
- Como todo va cifrado, privado.js (pendientes con detalle) ya se publica dentro del cifrado. Actualizar sus pendientes desde el Artifact 'Pendientes y Tareas' antes de publicar.
- Para cambiar la clave: editar clave.txt y publicar de nuevo (los dispositivos tendrán que escribirla otra vez).

## Refresco en la nube (26 oct 2026)

- El workflow de GitHub Actions ejecuta `actualizar.py --ia-nube`, luego `preparar_publico.py` y publica el HTML cifrado en GitHub Pages. Si no obtiene ninguna noticia ni cotización, falla y no despliega; los fallos parciales se muestran como avisos.
- Los resúmenes en la nube usan Gemini; el modo local predeterminado sigue usando LM Studio.
- Crear una clave en https://aistudio.google.com/apikey y guardarla como secreto de Actions `GEMINI_API_KEY`.
- El secreto es opcional: sin él se publica sin resúmenes y sin aviso de IA.
- Si Gemini falla, los demás temas continúan y aparece un único aviso: `Resumen IA no disponible para: IA, Bolsa` (según los temas afectados).
- Para fijar el modelo, definir la variable de entorno `GEMINI_MODEL`; si no, se consulta la lista disponible y se priorizan los modelos Flash indicados en el script.
- El refresco programado puede estar pausado (la sección `schedule` está comentada en el workflow); para reactivarlo, descomentar `schedule`. GitHub puede retrasar ejecuciones programadas. También permite ejecución manual con `workflow_dispatch`; evita solapamientos y tiene límite de 15 minutos.
- El repositorio debe ser público para GitHub Pages en el plan Free. Los secretos de Actions son `TABLERO_CLAVE` (mínimo 8 caracteres) y, opcionalmente, `GEMINI_API_KEY`. El generador usa `clave.txt` cuando existe y, en su ausencia, `TABLERO_CLAVE`.
- Pendientes ya no está en la web, ni siquiera dentro del cifrado. Vive en el Artifact «Pendientes y Tareas»; `data/privado.js` queda solo para la copia local con `ABRIR.bat`. Sin datos privados, la web oculta la pestaña Pendientes y el saludo personal.
- `publicar.bat` local ya no publica; el workflow usa el generador, que solo incrusta `data/publico.js`. `.staticrypt.json` se conserva en Git porque contiene únicamente la sal; la clave y los datos generados quedan excluidos.
- `programar_refresco.ps1` queda obsoleto y no se registra. Este cambio prepara el flujo: no crea repositorio remoto, no configura secretos y no publica por sí mismo.

## Falla de publicación del 19 nov 2026 (resuelta)
- Síntoma: el tablero quedó 20 h sin actualizarse. Los runs #69 y #70 (programados) fallaron solo en el paso «Publicar en GitHub Pages» con «No artifacts named "github-pages"», aunque el artefacto sí estaba subido.
- «Re-run jobs» del mismo run NO sirve: sube un segundo artefacto con el mismo nombre y falla con «Multiple artifacts named github-pages». Siempre lanzar un run nuevo (Actions → Run workflow → main).
- Arreglo (commit f39103e): `deploy-pages` v4→v5, `upload-pages-artifact` v3→v5, `configure-pages` v5→v6. Run #71 manual salió verde y el sitio se publicó. Causa raíz no confirmada (falla temporal de GitHub o versión vieja incompatible).
- Pendiente: confirmar que los programados siguientes salgan en verde. Los logs de Actions piden sesión en GitHub; el estado de runs, pasos y anotaciones se puede leer sin sesión por la API pública (`api.github.com/repos/diegopradoq-cpu/tablero/actions/runs`).
