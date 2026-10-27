"""Actualiza RSS y cotizaciones; resume con LM Studio o, si se pide, Gemini.

Uso:  python actualizar.py [--sin-ia | --ia-nube]
Escribe data/publico.js (noticias + mercados). Lo privado (Gmail, pendientes) vive
aparte en data/privado.js y NO se publica.
"""
import argparse
import calendar
import concurrent.futures as cf
import email.utils
import html
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

RAIZ = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (tablero-diego)"}
LM_URL = "http://localhost:1234/v1/chat/completions"
MODELO = "qwen/qwen3.5-9b"
SISTEMA_RESUMEN = "Eres un editor de noticias conciso. Respondes en español."
GEMINI_SEGUNDOS = 225  # Presupuesto compartido de descubrimiento, pausas y resúmenes.


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def limpiar(t):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()


def fecha(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def tag(el):
    return el.tag.split("}")[-1]


def leer_feed(nombre, url):
    raiz = ET.fromstring(get(url))
    items = []
    for it in raiz.iter():
        if tag(it) not in ("item", "entry"):
            continue
        d = {tag(c): c for c in it}
        link = ""
        if "link" in d:
            link = d["link"].get("href") or (d["link"].text or "")
        titulo = limpiar(d["title"].text) if "title" in d else ""
        desc = ""
        for k in ("description", "summary", "content", "encoded"):
            if k in d and d[k].text:
                desc = limpiar(d[k].text)[:400]
                if desc.startswith("Article URL"):  # Hacker News: la descripción es solo enlaces
                    desc = ""
                break
        f = None
        for k in ("pubDate", "published", "updated", "date"):
            if k in d:
                f = fecha(d[k].text)
                break
        if titulo and link:
            items.append({"titulo": titulo, "url": link.strip(), "fuente": nombre, "desc": desc, "fecha": f})
    return items


def noticias(cfg):
    limite = datetime.now(timezone.utc) - timedelta(hours=cfg["max_horas"])
    salida, errores = {}, []
    for clave, tema in cfg["temas"].items():
        with cf.ThreadPoolExecutor(8) as ex:
            futs = {ex.submit(leer_feed, n, u): n for n, u in tema["feeds"]}
            todos = []
            for f in cf.as_completed(futs):
                try:
                    todos += f.result()
                except Exception as e:  # un feed caído no tumba el resto
                    errores.append(f"{futs[f]}: {type(e).__name__}")
        vistos, unicos = set(), []
        for it in sorted(todos, key=lambda i: i["fecha"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
            if it["fecha"] and it["fecha"] < limite:
                continue
            k = re.sub(r"\W+", "", it["titulo"].lower())[:60]
            if k in vistos:
                continue
            vistos.add(k)
            unicos.append(it)
        # intercalar fuentes para que una sola no copie todo el tema
        por_fuente = {}
        for it in unicos:
            por_fuente.setdefault(it["fuente"], []).append(it)
        mezcla = []
        while any(por_fuente.values()) and len(mezcla) < cfg["por_tema"]:
            for lst in por_fuente.values():
                if lst and len(mezcla) < cfg["por_tema"]:
                    mezcla.append(lst.pop(0))
        mezcla.sort(key=lambda i: i["fecha"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        for it in mezcla:
            it["fecha"] = it["fecha"].isoformat() if it["fecha"] else None
        salida[clave] = {"nombre": tema["nombre"], "items": mezcla, "resumen": ""}
    return salida, errores


def cotizacion(nombre, simbolo, grupo=""):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(simbolo)}?range=1y&interval=1d"
    r = json.loads(get(url))["chart"]["result"][0]
    nombre_zona = r["meta"].get("exchangeTimezoneName")
    try:
        zona = ZoneInfo(nombre_zona) if nombre_zona else timezone.utc
        fecha_cierre = lambda t: datetime.fromtimestamp(t, zona).date()
    except ZoneInfoNotFoundError:
        # Python para Windows incluye la base IANA de Tcl en su biblioteca estándar.
        # No requiere instalar tzdata ni sustituye las reglas históricas por un offset fijo.
        import tkinter
        reloj = tkinter.Tcl()
        fecha_cierre = lambda t: datetime.strptime(
            reloj.call("clock", "format", t, "-timezone", ":" + nombre_zona, "-format", "%Y-%m-%d"),
            "%Y-%m-%d").date()
    puntos = [(fecha_cierre(t), p)
              for t, p in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if p is not None]
    precios = [p for _, p in puntos]
    ultimo = r["meta"].get("regularMarketPrice", precios[-1])
    fin = puntos[-1][0]
    mes = fin.month - 1 or 12
    anio = fin.year - (fin.month == 1)
    corte = fin.replace(year=anio, month=mes, day=min(fin.day, calendar.monthrange(anio, mes)[1]))
    previo = next((p for d, p in reversed(puntos) if d <= corte), precios[0])
    return {
        "nombre": nombre, "grupo": grupo, "simbolo": simbolo, "precio": round(ultimo, 2),
        "cambio_pct": round((ultimo / previo - 1) * 100, 2), "moneda": r["meta"].get("currency", ""),
        "serie": [round(p, 2) for p in precios[-22:]],
        "historico": {"fechas": [d.isoformat() for d, _ in puntos],
                      "precios": [round(p, 4 if p < 1 else 2) for p in precios]},
    }


def mercados(cfg):
    out, errores = [], []
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(cotizacion, n, s, g): (n, i) for i, (n, s, g) in enumerate(cfg["mercados"])}
        res = {}
        for f in cf.as_completed(futs):
            n, i = futs[f]
            try:
                res[i] = f.result()
            except Exception as e:
                errores.append(f"{n}: {type(e).__name__}")
    return [res[i] for i in sorted(res)], errores


def pedido_resumen(tema):
    """Solo titulares y descripciones públicas; compartido por ambos proveedores."""
    base = "\n".join(f"- {i['titulo']}. {i['desc'][:200]}" for i in tema["items"][:10])
    return (
        f"Tema: {tema['nombre']}. Con estos titulares recientes escribe un resumen en español de 3 a 4 "
        "viñetas (máx. 25 palabras cada una) de lo más importante. Solo usa lo que está en el texto; "
        "no inventes cifras ni hechos. Conserva en inglés los nombres propios y términos técnicos.\n\n" + base
    )


def resumir(tema):
    """Resumen en español de los titulares. Solo usa lo que dicen los feeds."""
    cuerpo = {
        "model": MODELO, "temperature": 0.2, "max_tokens": 600, "reasoning_effort": "none",
        "messages": [
            {"role": "system", "content": SISTEMA_RESUMEN},
            {"role": "user", "content": pedido_resumen(tema)},
        ],
    }
    req = urllib.request.Request(LM_URL, json.dumps(cuerpo).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


class SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # No reenviar la cabecera de autenticación a otra dirección.
        return None


def gemini_json(base, ruta, clave, fin, cuerpo=None):
    restante = fin - time.monotonic()
    if restante <= 0:
        raise TimeoutError("Presupuesto de IA agotado")
    req = urllib.request.Request(
        base + "/v1beta/" + ruta,
        data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={"x-goog-api-key": clave, "Content-Type": "application/json"},
    )
    with urllib.request.build_opener(SinRedireccion()).open(req, timeout=min(12, restante)) as r:
        return json.load(r)


def modelo_gemini(base, clave, fin):
    elegido = os.environ.get("GEMINI_MODEL", "").strip().removeprefix("models/")
    if elegido:
        return elegido
    disponibles, pagina = [], ""
    # Límite también para listas paginadas defectuosas.
    for _ in range(10):
        ruta = "models?pageSize=1000"
        if pagina:
            ruta += "&pageToken=" + urllib.request.quote(pagina, safe="")
        respuesta = gemini_json(base, ruta, clave, fin)
        disponibles.extend(
            m["name"].removeprefix("models/") for m in respuesta.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        )
        pagina = respuesta.get("nextPageToken")
        if not pagina:
            break
    for nombre in ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"):
        if nombre in disponibles:
            return nombre
    return next((m for m in disponibles if "flash-lite" in m), None)


def config_gemini(modelo):
    config = {"temperature": 0.2, "maxOutputTokens": 600}
    # REST: https://ai.google.dev/api/generate-content#ThinkingConfig
    if modelo.startswith(("gemini-2.5-flash-lite", "gemini-2.5-flash")):
        config["thinkingConfig"] = {"thinkingBudget": 0}
    elif modelo.startswith(("gemini-3.5-flash-lite", "gemini-3-flash", "gemini-3.1-flash-lite")):
        config["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
    return config


def texto_gemini(respuesta):
    if respuesta.get("promptFeedback", {}).get("blockReason"):
        raise ValueError("Respuesta bloqueada")
    candidato = respuesta["candidates"][0]
    if candidato.get("finishReason") not in (None, "STOP"):
        raise ValueError("Respuesta incompleta o bloqueada")
    texto = "\n".join(p["text"] for p in candidato["content"]["parts"]
                      if p.get("text") and not p.get("thought")).strip()
    if not texto or not re.search(r"(?m)^\s*(?:[-*•] |\d+[.)] )\S", texto):
        raise ValueError("Respuesta vacía o sin viñetas")
    return texto


def pausa_gemini(segundos, fin):
    if time.monotonic() + segundos >= fin:
        raise TimeoutError("Presupuesto de IA agotado")
    time.sleep(segundos)


def resumir_nube(temas):
    clave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not clave:
        return ""
    activos = [t for t in temas.values() if t["items"]]
    if not activos:
        return ""
    base = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
    fin = time.monotonic() + GEMINI_SEGUNDOS
    errores_api = (OSError, http.client.HTTPException, ValueError, KeyError,
                   IndexError, TypeError, AttributeError)
    try:
        modelo = modelo_gemini(base, clave, fin)
    except errores_api:
        modelo = None
    fallidos, ultimo = [], None
    for tema in activos:
        try:
            if not modelo:
                raise ValueError("Sin modelo disponible")
            cuerpo = {
                "contents": [{"role": "user", "parts": [{"text": pedido_resumen(tema)}]}],
                "systemInstruction": {"parts": [{"text": SISTEMA_RESUMEN}]},
                "generationConfig": config_gemini(modelo),
            }
            for intento in range(2):
                if ultimo is not None:
                    pausa_gemini(max(0, 5 - (time.monotonic() - ultimo)), fin)
                ultimo = time.monotonic()
                try:
                    respuesta = gemini_json(base, "models/" + urllib.request.quote(modelo, safe="")
                                            + ":generateContent", clave, fin, cuerpo)
                    tema["resumen"] = texto_gemini(respuesta)
                    break
                except urllib.error.HTTPError as e:
                    if intento or (e.code != 429 and not 500 <= e.code <= 599):
                        raise
                    espera = e.headers.get("Retry-After", "10")
                    try:
                        espera = float(espera)
                    except ValueError:
                        fecha_reintento = fecha(espera)
                        espera = ((fecha_reintento - datetime.now(timezone.utc)).total_seconds()
                                  if fecha_reintento else 10)
                    pausa_gemini(min(60, max(5, espera)), fin)
        except errores_api:
            # Nunca registrar excepciones, cuerpos ni cabeceras del proveedor.
            tema["resumen"] = ""
            fallidos.append(tema["nombre"])
    return "Resumen IA no disponible para: " + ", ".join(fallidos) if fallidos else ""


def main():
    ap = argparse.ArgumentParser()
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--sin-ia", action="store_true")
    modo.add_argument("--ia-nube", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((RAIZ / "feeds.json").read_text(encoding="utf-8"))

    temas, err_n = noticias(cfg)
    mercs, err_m = mercados(cfg)
    if not any(t["items"] for t in temas.values()) and not mercs:
        for error in err_n + err_m:
            print(f"  - feed caído: {error}")
        sys.exit("ERROR: no se obtuvieron noticias ni cotizaciones. No se actualizan los datos.")
    aviso_ia = ""
    if a.ia_nube:
        aviso_ia = resumir_nube(temas)
    elif not a.sin_ia:
        try:
            for t in temas.values():
                if t["items"]:
                    t["resumen"] = resumir(t)
        except (urllib.error.URLError, OSError, KeyError):
            aviso_ia = "IA local apagada: sin resúmenes (ejecutar ia-local\\INICIAR-IA.bat)"

    datos = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "temas": temas, "mercados": mercs,
        "avisos": [x for x in [aviso_ia] if x] + [f"feed caído: {e}" for e in err_n + err_m],
    }
    (RAIZ / "data").mkdir(exist_ok=True)
    (RAIZ / "data" / "publico.js").write_text(
        "window.PUBLICO = " + json.dumps(datos, ensure_ascii=False) + ";\n", encoding="utf-8")
    n = sum(len(t["items"]) for t in temas.values())
    print(f"OK: {n} noticias, {len(mercs)} cotizaciones, {len(datos['avisos'])} avisos")
    for av in datos["avisos"]:
        print("  -", av)


if __name__ == "__main__":
    sys.exit(main())
