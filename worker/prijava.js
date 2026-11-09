// Cloudflare Worker "gigomat-prijava": prima prijave koncerata s gigomat.com/prijavi.html
// i šalje ih e-mailom na info adresu (preko Email Routinga, binding PRIJAVE).
// Ne sprema ništa; poruka je jedino mjesto gdje prijava postoji.
//
// Uz to "Moji koncerti u kalendaru" (KV binding MOJI):
//   POST /moji        {token, ids:[...], rem}  -> sprema popis zvjezdica uređaja (bez imena i e-maila)
//   GET  /cal/<id>.ics                         -> osobni kalendar za pretplatu (Google, Apple, Outlook)
// id = prvih 20 znakova SHA-256(token): link na kalendar je javan, ali bez tokena nitko ne može mijenjati popis.
import { EmailMessage } from "cloudflare:email";

const FROM = "prijave@gigomat.com";
const TO = "gigomat.com@gmail.com";            // mora biti potvrđena odredišna adresa u Email Routingu
const ALLOWED = ["https://gigomat.com", "https://www.gigomat.com"];

function b64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
const one = (v, n = 500) => String(v ?? "").replace(/[\r\n]+/g, " ").trim().slice(0, n);

const SITE = "https://gigomat.com/";

async function sha(t) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t));
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 20);
}
const icsEsc = s => String(s ?? "").replace(/\\/g, "\\\\").replace(/[;,]/g, m => "\\" + m).replace(/\r?\n/g, "\\n");
function fold(line) {
  const out = []; let cur = "";
  for (const ch of line) { if (new TextEncoder().encode(cur + ch).length > 73) { out.push(cur); cur = " " + ch; } else cur += ch; }
  out.push(cur); return out.join("\r\n");
}
async function siteData() {
  const cache = caches.default, key = new Request(SITE + "events.json");
  let r = await cache.match(key);
  if (!r) {
    r = await fetch(SITE + "events.json", { cf: { cacheTtl: 3600 } });
    if (!r.ok) throw new Error("events");
    r = new Response(r.body, r); r.headers.set("Cache-Control", "max-age=3600");
    await cache.put(key, r.clone());
  }
  return r.json();
}
async function calendar(id, env) {
  const raw = await env.MOJI.get("u:" + id);
  const mine = raw ? JSON.parse(raw) : { ids: [], rem: "2880,180" };
  const data = await siteData();
  const want = new Set(mine.ids || []);
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Gigomat//HR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    "X-WR-CALNAME:Moji koncerti (Gigomat)", "X-WR-TIMEZONE:Europe/Zagreb",
    "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H",
    "BEGIN:VTIMEZONE", "TZID:Europe/Zagreb",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST", "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET", "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
    "END:VTIMEZONE"];
  const rem = String(mine.rem ?? "2880,180").split(",").filter(Boolean);
  for (const e of data.events) {
    if (!want.has(e.id)) continue;
    const v = data.venues[e.venue] || {};
    const city = (data.cities[v.city || "zagreb"] || {}).name || "";
    const d = e.date.replace(/-/g, "");
    let when;
    if (e.time) {
      const [h, m] = e.time.split(":").map(Number);
      const end = new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8), h + 3, m));
      const p = n => String(n).padStart(2, "0");
      when = [`DTSTART;TZID=Europe/Zagreb:${d}T${p(h)}${p(m)}00`,
        `DTEND;TZID=Europe/Zagreb:${end.getUTCFullYear()}${p(end.getUTCMonth() + 1)}${p(end.getUTCDate())}T${p(end.getUTCHours())}${p(end.getUTCMinutes())}00`];
    } else {
      const n = new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8) + 1)).toISOString().slice(0, 10).replace(/-/g, "");
      when = [`DTSTART;VALUE=DATE:${d}`, `DTEND;VALUE=DATE:${n}`];
    }
    const loc = [v.name, v.address, city].filter(Boolean).join(", ");
    const alarms = rem.flatMap(m => ["BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${icsEsc(e.title)}`,
      `TRIGGER:-PT${e.time ? m : (m === "180" ? 0 : Number(m) - 720)}M`, "END:VALARM"]);
    lines.push("BEGIN:VEVENT", `UID:${e.id}@koncerti-zagreb`, `DTSTAMP:${stamp}`, ...when,
      `SUMMARY:${icsEsc(e.title)}`, `LOCATION:${icsEsc(loc)}`,
      `DESCRIPTION:${icsEsc((e.url ? "Ulaznice i info: " + e.url + "\n" : "") + SITE + "k/" + e.id + "/")}`,
      ...(e.url ? [`URL:${e.url}`] : []), ...alarms, "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return lines.map(fold).join("\r\n") + "\r\n";
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const m = url.pathname.match(/^\/cal\/([a-f0-9]{20})\.ics$/);
    if (m && req.method === "GET") {
      try {
        return new Response(await calendar(m[1], env), { headers: {
          "Content-Type": "text/calendar; charset=utf-8", "Cache-Control": "max-age=900",
          "Access-Control-Allow-Origin": "*" } });
      } catch (e) { return new Response("Kalendar trenutno nije dostupan", { status: 503 }); }
    }
    const origin = req.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": ALLOWED.includes(origin) ? origin : ALLOWED[0],
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    };
    const reply = (obj, status = 200) =>
      new Response(JSON.stringify(obj), { status, headers: { ...cors, "Content-Type": "application/json" } });

    if (req.method === "OPTIONS") return new Response(null, { headers: cors });

    if (url.pathname === "/moji" && req.method === "POST") {
      if (!ALLOWED.includes(origin)) return reply({ ok: false, error: "nedopušteno" }, 403);
      let d;
      try { d = await req.json(); } catch { return reply({ ok: false }, 400); }
      const token = String(d.token || "");
      if (!/^[a-f0-9]{32,64}$/.test(token)) return reply({ ok: false, error: "token" }, 400);
      const ids = (Array.isArray(d.ids) ? d.ids : []).map(String).filter(x => /^[a-z0-9-]{1,40}$/i.test(x)).slice(0, 500);
      const rem = /^[0-9,]{0,20}$/.test(String(d.rem ?? "")) ? String(d.rem ?? "") : "2880,180";
      const id = await sha(token);
      // neaktivan popis nestaje sam nakon 2 godine
      await env.MOJI.put("u:" + id, JSON.stringify({ ids, rem, at: new Date().toISOString().slice(0, 10) }), { expirationTtl: 63072000 });
      return reply({ ok: true, id });
    }
    if (req.method !== "POST") return new Response("Gigomat: prijave koncerata", { headers: cors });
    if (!ALLOWED.includes(origin)) return reply({ ok: false, error: "nedopušteno" }, 403);

    let d;
    try { d = await req.json(); } catch { return reply({ ok: false, error: "neispravan zahtjev" }, 400); }

    // Zaštita od robota: skriveno polje mora biti prazno, a obrazac se ne ispunjava za manje od 3 s
    if (d.web || Number(d.ms) < 3000) return reply({ ok: true });

    for (const k of ["izvodjac", "datum", "prostor", "grad"]) {
      if (!one(d[k])) return reply({ ok: false, error: "nedostaje " + k }, 400);
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(one(d.datum))) return reply({ ok: false, error: "neispravan datum" }, 400);

    const fields = [
      ["Izvođač", d.izvodjac], ["Datum", d.datum], ["Početak", d.vrijeme], ["Prostor", d.prostor],
      ["Grad", d.grad], ["Poveznica", d.link], ["Cijena", d.cijena], ["Žanr", d.zanr],
      ["Napomena", one(d.napomena, 1000)], ["Kontakt", d.kontakt],
    ].filter(([, v]) => one(v)).map(([k, v]) => `${k}: ${one(v, 1000)}`);
    const body = fields.join("\n") + "\n\n— poslano s gigomat.com/prijavi.html";
    const subject = `Prijava koncerta: ${one(d.izvodjac, 80)} (${one(d.datum)}, ${one(d.grad, 30)})`;
    const contact = one(d.kontakt, 200);
    const replyTo = /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(contact) ? contact : "";

    const raw = [
      `From: Gigomat prijave <${FROM}>`,
      `To: ${TO}`,
      ...(replyTo ? [`Reply-To: ${replyTo}`] : []),
      `Subject: =?UTF-8?B?${b64(subject)}?=`,
      `Date: ${new Date().toUTCString()}`,
      `Message-ID: <${crypto.randomUUID()}@gigomat.com>`,
      "MIME-Version: 1.0",
      "Content-Type: text/plain; charset=UTF-8",
      "Content-Transfer-Encoding: base64",
      "",
      b64(body).replace(/.{76}/g, "$&\r\n"),
    ].join("\r\n");

    try {
      await env.PRIJAVE.send(new EmailMessage(FROM, TO, raw));
    } catch (e) {
      return reply({ ok: false, error: "slanje nije uspjelo" }, 502);
    }
    return reply({ ok: true });
  },
};
