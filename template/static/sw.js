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

// ---------- Podsjetnici za koncerte označene zvjezdicom ----------
// Popis sprema aplikacija u cache "koncerti-moji"; ovdje ga provjeravamo i javljamo.
const zgDate = (d) => new Intl.DateTimeFormat("en-CA", {timeZone: "Europe/Zagreb"}).format(d);
async function checkMine(){
  const c = await caches.open("koncerti-moji");
  const r = await c.match("moji.json"); if (!r) return;
  const {rem, events} = await r.json(); if (!rem || !events || !events.length) return;
  const sent = await c.match("sent.json").then(x => x ? x.json() : {}).catch(() => ({}));
  const now = new Date(), today = zgDate(now), tomorrow = zgDate(new Date(now.getTime() + 864e5)), in2 = zgDate(new Date(now.getTime() + 2 * 864e5));
  const hm = new Intl.DateTimeFormat("en-GB", {timeZone: "Europe/Zagreb", hour: "2-digit", minute: "2-digit", hour12: false}).format(now);
  const mins = (t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
  for (const e of events){
    let key = "", when = "";
    if (rem.includes("2880") && e.date === in2){ key = e.id + ":d2"; when = "Prekosutra" + (e.time ? " u " + e.time : ""); }
    if (rem.includes("1440") && e.date === tomorrow){ key = e.id + ":d"; when = "Sutra" + (e.time ? " u " + e.time : ""); }
    if (e.date === today && (rem.includes("180") || rem === "1440" || rem === "2880")){
      // na dan koncerta: ako je odabrano "3 sata prije", javi tek kad je blizu
      const close = !e.time || !rem.includes("180") || mins(e.time) - mins(hm) <= 240;
      if (close && (!e.time || mins(e.time) > mins(hm) - 30)){ key = e.id + ":t"; when = "Danas" + (e.time ? " u " + e.time : ""); }
    }
    if (!key || sent[key]) continue;
    await self.registration.showNotification(e.artist, {body: when + " · " + e.venue, tag: key, icon: "icon-192.png", badge: "icon-192.png", data: {id: e.id}});
    sent[key] = today;
  }
  // stare zapise brišemo da popis ne raste
  for (const k of Object.keys(sent)) if (sent[k] < zgDate(new Date(now.getTime() - 7 * 864e5))) delete sent[k];
  await c.put("sent.json", new Response(JSON.stringify(sent)));
}
self.addEventListener("periodicsync", e => { if (e.tag === "moji") e.waitUntil(checkMine()); });
self.addEventListener("message", e => { if (e.data === "check") e.waitUntil(checkMine()); });
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(list => {
    for (const w of list) if ("focus" in w) return w.focus();
    return self.clients.openWindow("./");
  }));
});
