"""Actualiza el tablero: baja RSS, cotizaciones y resume con la IA local (LM Studio).

Uso:  python actualizar.py [--sin-ia]
Escribe data/publico.js (noticias + mercados). Lo privado (Gmail, pendientes) vive
aparte en data/privado.js y NO se publica.
"""
import argparse
import concurrent.futures as cf
import email.utils
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (tablero-diego)"}
LM_URL = "http://localhost:1234/v1/chat/completions"
MODELO = "qwen/qwen3.5-9b"


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
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(simbolo)}?range=1mo&interval=1d"
    r = json.loads(get(url))["chart"]["result"][0]
    precios = [p for p in r["indicators"]["quote"][0]["close"] if p is not None]
    ultimo = r["meta"].get("regularMarketPrice", precios[-1])
    previo = r["meta"].get("chartPreviousClose") or precios[-2]
    return {
        "nombre": nombre, "grupo": grupo, "simbolo": simbolo, "precio": round(ultimo, 2),
        "cambio_pct": round((ultimo / previo - 1) * 100, 2), "moneda": r["meta"].get("currency", ""),
        "serie": [round(p, 2) for p in precios[-22:]],
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


def resumir(tema):
    """Resumen en español de los titulares. Solo usa lo que dicen los feeds."""
    base = "\n".join(f"- {i['titulo']}. {i['desc'][:200]}" for i in tema["items"][:10])
    pedido = (
        f"Tema: {tema['nombre']}. Con estos titulares recientes escribe un resumen en español de 3 a 4 "
        "viñetas (máx. 25 palabras cada una) de lo más importante. Solo usa lo que está en el texto; "
        "no inventes cifras ni hechos. Conserva en inglés los nombres propios y términos técnicos.\n\n" + base
    )
    cuerpo = {
        "model": MODELO, "temperature": 0.2, "max_tokens": 600, "reasoning_effort": "none",
        "messages": [
            {"role": "system", "content": "Eres un editor de noticias conciso. Respondes en español."},
            {"role": "user", "content": pedido},
        ],
    }
    req = urllib.request.Request(LM_URL, json.dumps(cuerpo).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-ia", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((RAIZ / "feeds.json").read_text(encoding="utf-8"))

    temas, err_n = noticias(cfg)
    mercs, err_m = mercados(cfg)
    if not any(t["items"] for t in temas.values()) and not mercs:
        for error in err_n + err_m:
            print(f"  - feed caído: {error}")
        sys.exit("ERROR: no se obtuvieron noticias ni cotizaciones. No se actualizan los datos.")
    aviso_ia = ""
    if not a.sin_ia:
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
