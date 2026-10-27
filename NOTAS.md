# Tablero de Diego
Noticias (IA, tecnología, bolsa, política mundial), mercados, guardados, tareas y pendientes.
- `ABRIR.bat`: actualiza datos (RSS + cotizaciones + resumen con LM Studio) y abre el servidor local.
- `feeds.json`: fuentes y watchlist; editar aquí.
- `data/publico.js` (generado) se publica; `data/privado.js` (Gmail/Calendar/pendientes) NUNCA se publica.
- `preparar_publico.py` arma dist/ sin lo privado; `publicar.bat` publica esa carpeta en Netlify.
- Tareas y guardados viven en localStorage del navegador (no sincronizan entre dispositivos).

## Publicar

Preparación una sola vez, desde una terminal en esta carpeta:

1. Si faltan `node` o `npx`, instalar Node.js LTS desde https://nodejs.org/ y abrir una terminal nueva. Comprobar con `node --version` y `npx.cmd --version`.
2. Ejecutar `npx.cmd netlify-cli login` y autorizar la cuenta en el navegador.
3. Ejecutar `npx.cmd netlify-cli init` para crear/configurar el sitio, o `npx.cmd netlify-cli link` si ya existe. La carpeta que se publica es `dist` y no hay comando de build.

Después ejecutar `publicar.bat`: actualiza noticias, cotizaciones y resúmenes, prepara `dist` y publica con `--prod --dir=dist --no-build`. Usa Netlify del PATH o, si falta, `npx netlify-cli`. Ante un fallo detiene la publicación; comprueba que `dist/data/privado.js` no exista. Si LM Studio está apagado, el actualizador puede continuar sin resúmenes y con un aviso.

El refresco automático pasa a GitHub Actions (ver sección del 26 oct 2026). `programar_refresco.ps1` queda obsoleto: no registrar la tarea local. Si ya existiera, se puede eliminar ejecutando `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\programar_refresco.ps1 -Quitar`.

Los scripts se entregan sin iniciar sesión, desplegar ni registrar la tarea automáticamente.

## Pendiente de mejora (v1 aprobada como borrador, 22 oct 2026)
- Configurar los secretos del repositorio privado para el refresco en GitHub Actions.
- Revisar la vista en teléfono (solo se probó en escritorio).
- Filtrar ruido de MarketWatch/Bolsa; afinar fuentes por tema.
- Llenar Hoy (Gmail + Calendar) pidiéndoselo a Claude; decidir login si va a la web.
- Sincronizar guardados y tareas entre dispositivos (hoy son localStorage).

## Rediseño del 22 oct 2026 (publicado el 22 oct 2026 junto con la ronda 4)
- Referencias: Glance (37k estrellas, AGPL, necesita servidor), Homepage (GPL), Dashy (MIT, pesado). Ninguno se puede copiar a un HTML estático, así que se aplicaron sus principios de legibilidad al HTML propio (encargo en `trabajo/encargo-codex-1-rediseno.md`; respaldo anterior en `trabajo/index.antes.html`).
- Cambios: tarjetas de 3 columnas, una sola tipografía, tema claro/oscuro con botón, barra de pestañas inferior en móvil, resumen IA plegable, aviso si los datos tienen más de 12 h, cinta de mercados con botón Pausar.
- Para publicarlo: `publicar.bat`.
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
- preparar_publico.py junta index.html + publico.js + privado.js en UN solo HTML y lo cifra con StatiCrypt (clave en clave.txt, local, nunca se publica; .staticrypt.json guarda la sal para que 'Recordarme' siga valiendo tras cada publicación).
- publicar.bat se cancela si dist/ tiene algo en claro. La web pide la clave al abrir.
- Como todo va cifrado, privado.js (pendientes con detalle) ya se publica dentro del cifrado. Actualizar sus pendientes desde el Artifact 'Pendientes y Tareas' antes de publicar.
- Para cambiar la clave: editar clave.txt y publicar de nuevo (los dispositivos tendrán que escribirla otra vez).

## Refresco en la nube (26 oct 2026)

- `.github/workflows/refrescar.yml` ejecuta `actualizar.py --sin-ia`, prepara un único HTML cifrado y publica `dist/index.html` en Netlify. No usa LM Studio ni genera resúmenes en la nube. Si no obtiene ninguna noticia ni cotización, falla y no despliega; los fallos parciales se muestran como avisos.
- Horarios de Lima: 06:00, 09:00, 12:00, 15:00, 18:00 y 21:00 (cron UTC: `0 11,14,17,20,23,2 * * *`). GitHub puede retrasar ejecuciones programadas. También permite ejecución manual con `workflow_dispatch`; evita solapamientos y tiene límite de 15 minutos.
- Se necesita un repositorio privado y sus secretos de Actions `TABLERO_CLAVE` (mínimo 8 caracteres) y `NETLIFY_AUTH_TOKEN`. El sitio está fijado como `c5bda084-84cb-48de-a242-04d9a2e9b463`. El generador usa `clave.txt` cuando existe y, en su ausencia, `TABLERO_CLAVE`.
- Pendientes ya no está en la web, ni siquiera dentro del cifrado. Vive en el Artifact «Pendientes y Tareas»; `data/privado.js` queda solo para la copia local con `ABRIR.bat`. Sin datos privados, la web oculta la pestaña Pendientes y el saludo personal.
- `publicar.bat` local ahora tampoco publica pendientes: usa el mismo generador, que solo incrusta `data/publico.js`. `.staticrypt.json` se conserva en Git porque contiene únicamente la sal; la clave y los datos generados quedan excluidos.
- `programar_refresco.ps1` queda obsoleto y no se registra. Este cambio prepara el flujo: no crea repositorio remoto, no configura secretos y no publica por sí mismo.
