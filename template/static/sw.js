// Service worker: aplikacija radi i bez interneta (zadnji preuzeti program),
// a kad ima mreže uvijek prikazuje svježe podatke.
const CACHE = "koncerti-__VERSION__";
const CORE = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  // Kalendari i RSS idu uvijek s mreže (čitaju ih kalendari, ne aplikacija)
  if (url.pathname.includes("/cal/") || url.pathname.includes("/rss/")) return;
  // Stranica i podaci: prvo mreža, a bez mreže zadnja spremljena verzija
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }
        return res;
      })
      .catch(() => caches.match(e.request).then(r => r || caches.match("./index.html")))
  );
});
