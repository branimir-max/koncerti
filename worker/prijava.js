// Cloudflare Worker "gigomat-prijava": prima prijave koncerata s gigomat.com/prijavi.html
// i šalje ih e-mailom na info adresu (preko Email Routinga, binding PRIJAVE).
// Ne sprema ništa; poruka je jedino mjesto gdje prijava postoji.
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

export default {
  async fetch(req, env) {
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
