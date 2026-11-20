// Service worker del Tablero. La pagina publicada ya viene cifrada (StatiCrypt), asi que
// lo que se guarda aqui es texto cifrado: sin la clave no se lee.
const CACHE = 'tablero-v1';
const BASE = ['./', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  if (req.mode === 'navigate') {
    // Pagina: red primero (siempre lo ultimo publicado); sin red, la ultima copia guardada.
    e.respondWith(
      fetch(req, { cache: 'no-cache' })
        .then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(x => x.put('./', c)); } return r; })
        .catch(() => caches.match('./'))
    );
    return;
  }
  // Iconos y manifiesto: de cache, y se refrescan en segundo plano.
  e.respondWith(
    caches.match(req).then(hit => {
      const red = fetch(req).then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(x => x.put(req, c)); } return r; }).catch(() => hit);
      return hit || red;
    })
  );
});
