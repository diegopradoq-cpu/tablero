"""Tablero local. Ejecutar con Python; Ctrl+C en esta ventana para apagarlo."""
import http.client
import html
import ipaddress
import json
import os
import queue
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urljoin, urlunsplit
import xml.etree.ElementTree as ET

RAIZ = Path(__file__).resolve().parent
LOCK = threading.Lock()
AUTORIDADES = {'127.0.0.1:8765', 'localhost:8765'}
ARCHIVOS = {'/index.html': 'text/html; charset=utf-8',
            '/data/publico.js': 'text/javascript; charset=utf-8',
            '/data/privado.js': 'text/javascript; charset=utf-8'}
MAX_BYTES = 2 * 1024 * 1024


class Problema(Exception):
    def __init__(self, mensaje, status=422):
        self.status = status
        super().__init__(mensaje)


def destino(url, timeout=10):
    if not isinstance(url, str) or len(url) > 300 or any(ord(c) <= 32 for c in url):
        raise Problema('La dirección debe tener como máximo 300 caracteres y no contener espacios.')
    try:
        p = urlsplit(url)
        if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.fragment:
            raise ValueError()
        port = p.port or (443 if p.scheme == 'https' else 80)
        answers = queue.Queue(maxsize=1)
        def resolver():
            try:
                answers.put(socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM))
            except OSError as e:
                answers.put(e)
        threading.Thread(target=resolver, daemon=True).start()
        try:
            records = answers.get(timeout=max(0.001, timeout))
        except queue.Empty:
            raise Problema('El servidor del feed no respondió a tiempo.')
        if isinstance(records, OSError):
            raise records
        ips = list(dict.fromkeys(a[4][0] for a in records))
    except (ValueError, OSError):
        raise Problema('Dirección inválida o el servidor no respondió. Usa una dirección https:// de RSS.')
    for ip in ips:
        address = ipaddress.ip_address(ip)
        if getattr(address, 'ipv4_mapped', None):
            address = address.ipv4_mapped
        test_loop = os.environ.get('TABLERO_TEST_PERMITIR_LOOPBACK') == '1' and address.is_loopback
        if (not address.is_global or address.is_multicast or address.is_reserved) and not test_loop:
            raise Problema('No se permiten direcciones de redes privadas, locales ni de metadata.')
    if not ips:
        raise Problema('El servidor no respondió.')
    return p, port, ips[0]


def canonical(url):
    p = urlsplit(url)
    port = p.port
    host = (p.hostname or '').lower()
    if ':' in host:
        host = '[' + host + ']'
    if port and port != (443 if p.scheme.lower() == 'https' else 80):
        host += ':' + str(port)
    return urlunsplit((p.scheme.lower(), host, p.path or '/', p.query, ''))


def descargar(url):
    deadline = time.monotonic() + 10
    redirects = 0
    fallback = None
    insecure_allowed = set()
    while True:
        p, port, ip = destino(url, deadline - time.monotonic())
        # HTTP solo se usa cuando la misma dirección HTTPS no está disponible.
        if p.scheme == 'http' and url not in insecure_allowed:
            secure = urlunsplit(('https', p.netloc, p.path, p.query, ''))
            fallback = url
            url = secure
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        conn = http.client.HTTPConnection(p.hostname, port, timeout=remaining)
        try:
            # Fijar la IP ya validada: la conexión no vuelve a resolver el host (DNS rebinding).
            conn.sock = socket.create_connection((ip, port), timeout=remaining)
            if p.scheme == 'https':
                conn.sock = ssl.create_default_context().wrap_socket(conn.sock, server_hostname=p.hostname)
            path = urlunsplit(('', '', p.path or '/', p.query, ''))
            conn.request('GET', path, headers={'User-Agent': 'TableroDiego/1.0', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                if redirects >= 3 or not response.getheader('Location'):
                    raise Problema('El feed tiene demasiadas redirecciones (máximo 3).')
                url = urljoin(url, response.getheader('Location'))
                redirects += 1
                fallback = None
                continue
            if response.status != 200:
                raise Problema('El servidor del feed respondió con un error HTTP.')
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                if conn.sock:
                    conn.sock.settimeout(remaining)
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    return b''.join(chunks), url
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise Problema('El feed supera el máximo de 2 MB.')
        except (OSError, http.client.HTTPException):
            if fallback:
                url = fallback
                insecure_allowed.add(url)
                fallback = None
                continue
            raise
        finally:
            conn.close()


def texto(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', html.unescape(value))).strip()[:60]


def comprobar(url):
    try:
        data, final = descargar(url)
    except (OSError, http.client.HTTPException):
        raise Problema('El servidor del feed no respondió o falló la conexión segura.')
    # También detectar declaraciones codificadas como UTF-16/32 antes del parser.
    upper = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper:
        raise Problema('El feed contiene DOCTYPE o entidades no permitidas.')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise Problema('No parece un feed RSS o Atom válido.')
    tag = lambda e: e.tag.split('}')[-1]
    if tag(root) not in ('rss', 'feed', 'RDF'):
        raise Problema('No parece un feed RSS o Atom válido.')
    items = sum(tag(e) in ('item', 'entry') for e in root.iter())
    if not items:
        raise Problema('El feed RSS o Atom no tiene ningún ítem.')
    parent = next((e for e in root if tag(e) == 'channel'), root)
    title = next((''.join(e.itertext()) for e in parent if tag(e) == 'title'), '')
    return texto(title) or 'Fuente RSS', items, final


def atomico(path, data):
    fd, temp = tempfile.mkstemp(prefix='.fuentes-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def cambiar(payload, borrar=False):
    with LOCK:
        path = RAIZ / 'feeds.json'
        original = path.read_bytes()
        cfg = json.loads(original)
        tema, url = payload.get('tema'), payload.get('url')
        if not isinstance(tema, str) or tema not in cfg['temas']:
            raise Problema('El tema indicado no existe.')
        if not isinstance(url, str):
            raise Problema('Falta la dirección del feed.')
        feeds = cfg['temas'][tema]['feeds']
        nombre, items = '', 0
        if borrar:
            found = next((f for f in feeds if f[1] == url), None)
            if not found:
                raise Problema('La fuente no existe en este tema.')
            if len(feeds) <= 1:
                raise Problema('Debe quedar al menos una fuente por tema.')
            nombre = found[0]
            feeds.remove(found)
        else:
            try:
                duplicate = any(canonical(url) == canonical(f[1]) for t in cfg['temas'].values() for f in t['feeds'])
            except ValueError:
                raise Problema('La dirección del feed no es válida.')
            if duplicate:
                raise Problema('Esta dirección ya está agregada en un tema.')
            supplied = payload.get('nombre', '')
            if not isinstance(supplied, str):
                raise Problema('El nombre debe ser texto.')
            nombre, items, final = comprobar(url)
            if any(canonical(final) == canonical(f[1]) for t in cfg['temas'].values() for f in t['feeds']):
                raise Problema('El destino del feed ya está agregado en un tema.')
            nombre = texto(supplied) or nombre
            feeds.append([nombre, final])
        backup_dir = RAIZ / 'trabajo'
        backup_dir.mkdir(exist_ok=True)
        now = datetime.now()
        if not list(backup_dir.glob('feeds.antes-' + now.strftime('%Y%m%d') + '-*.json')):
            (backup_dir / ('feeds.antes-' + now.strftime('%Y%m%d-%H%M%S') + '.json')).write_bytes(original)
        source = original.decode('utf-8')
        match = re.search(r'\n([ \t]+)"', source)
        indent = match.group(1) if match else 2
        output = json.dumps(cfg, ensure_ascii=False, indent=indent)
        if source.endswith('\n'):
            output += '\n'
        if b'\r\n' in original:
            output = output.replace('\n', '\r\n')
        # Restaurar también los datos si el actualizador falla después de escribirlos.
        public = RAIZ / 'data' / 'publico.js'
        previous = public.read_bytes() if public.exists() else None
        atomico(path, output.encode('utf-8'))
        try:
            subprocess.run([sys.executable, '-I', str(RAIZ / 'actualizar.py')], cwd=RAIZ,
                           timeout=180, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.SubprocessError, OSError):
            atomico(path, original)
            if previous is not None:
                atomico(public, previous)
            elif public.exists():
                public.unlink()
            raise Problema('No se pudieron actualizar los datos. Se restauraron las fuentes anteriores.', 500)
        print(json.dumps({'cambio': 'quitar' if borrar else 'agregar', 'tema': tema, 'nombre': nombre}, ensure_ascii=True), flush=True)
        return {'ok': True, 'nombre': nombre, 'items': items}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(json.dumps({'http': fmt % args}, ensure_ascii=True), flush=True)

    def responder(self, status, data, content='application/json; charset=utf-8'):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8') if not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get('Host') not in AUTORIDADES:
            return self.responder(403, {'error': 'Host no permitido.'})
        if self.path == '/api/fuentes':
            with LOCK:
                cfg = json.loads((RAIZ / 'feeds.json').read_text(encoding='utf-8'))
            return self.responder(200, {k: [{'nombre': n, 'url': u} for n, u in t['feeds']] for k, t in cfg['temas'].items()})
        if self.path not in ARCHIVOS or not (RAIZ / self.path[1:]).is_file():
            return self.responder(404, {'error': 'Archivo no disponible.'})
        self.responder(200, (RAIZ / self.path[1:]).read_bytes(), ARCHIVOS[self.path])

    def mutar(self, borrar=False):
        if (self.headers.get('Host') not in AUTORIDADES or
                self.headers.get('Origin') not in {'http://' + h for h in AUTORIDADES} or
                self.headers.get_content_type() != 'application/json'):
            return self.responder(403, {'error': 'Origen, Host o tipo de contenido no permitido.'})
        if self.path != '/api/fuentes':
            return self.responder(404, {'error': 'Ruta no disponible.'})
        try:
            self.connection.settimeout(10)
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192 or self.headers.get('Transfer-Encoding'):
                raise Problema('El cuerpo JSON no es válido.', 400)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError()
            result = cambiar(payload, borrar)
        except Problema as e:
            return self.responder(e.status, {'error': str(e)})
        except (ValueError, UnicodeError, TimeoutError):
            return self.responder(400, {'error': 'El cuerpo JSON no es válido o no llegó a tiempo.'})
        except Exception:
            return self.responder(500, {'error': 'No se pudo completar el cambio de fuentes.'})
        self.responder(200, result)

    def do_POST(self):
        self.mutar()

    def do_DELETE(self):
        self.mutar(True)


if __name__ == '__main__':
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    except OSError:
        sys.exit('El puerto 8765 ya está ocupado. No se inició otro servidor.')
    print('Tablero: http://127.0.0.1:8765/index.html — Ctrl+C para apagar.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
