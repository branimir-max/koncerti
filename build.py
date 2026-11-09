"""Spoji ručne i automatski skupljene podatke i izgradi stranicu: python build.py

Ulaz:  data/venues.json, data/manual.json, data/scraped/*.json
Izlaz: site/index.html (aplikacija s ugrađenim podacima), site/events.json
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_URL = "https://branimir-max.github.io/koncerti/"  # promijeni kad dođe vlastita domena
DATA = ROOT / "data"
SITE = ROOT / "site"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^kset\d*:\s*", "", s)
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in {"the", "i", "and", "feat", "ft", "koncert", "live"}]
    return " ".join(words[:3])


def norm_all(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^kset\d*:\s*", "", s)
    stop = {"the", "i", "and", "feat", "ft", "koncert", "live", "u", "na", "x", "presents"}
    return [w for w in re.findall(r"[a-z0-9]+", s) if w not in stop]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm(s).replace(" ", ""))[:20] or "prostor"


def main() -> None:
    venues = json.loads((DATA / "venues.json").read_text())
    manual = json.loads((DATA / "manual.json").read_text())["events"]
    scraped = []
    for f in sorted((DATA / "scraped").glob("*.json")):
        scraped += json.loads(f.read_text())

    group = lambda k: venues.get(k, {}).get("group", k)  # noqa: E731
    today = date.today().isoformat()
    buckets: dict[tuple, list[dict]] = {}

    def same(a: str, b: str) -> bool:
        ta, tb = norm_all(a), norm_all(b)
        if not ta or not tb:
            return False
        fa = next((w for w in ta if len(w) >= 3), "")
        fb = next((w for w in tb if len(w) >= 3), "")
        if fa and fa == fb:
            return True
        sa, sb = set(ta), set(tb)
        return sa <= sb or sb <= sa or len(sa & sb) / len(sa | sb) >= 0.5

    def add(e: dict, prefer: bool) -> None:
        if not e.get("date") or e["date"] < today or not e.get("title"):
            return
        if e["date"] > (date.today() + timedelta(days=550)).isoformat():  # očito krivi datumi (npr. 2030.)
            return
        if not e.get("venue") or e["venue"] not in venues:
            name = e.get("venue_name") or e.get("venue") or ""
            if not name:
                return
            key = slug(name)
            venues.setdefault(key, {"name": name.strip(), "address": "", "auto": True})
            e["venue"] = key
        bucket = buckets.setdefault((e["date"], group(e["venue"])), [])
        for old in bucket:
            if same(old["title"], e["title"]):
                if prefer:  # automatski podaci su svježiji, ali ne brišu poznate vrijednosti
                    for f in ("time", "price", "url"):
                        if e.get(f):
                            old[f] = e[f]
                    if not old.get("genre") and e.get("genre"):  # ručno odabrani žanr ima prednost
                        old["genre"] = e["genre"]
                    # Konkretna dvorana (npr. Lisinski – Mala dvorana) ima prednost pred općim prostorom
                    if venues.get(e["venue"], {}).get("group"):
                        old["venue"] = e["venue"]
                return
        if not re.match(r"^https?://", e.get("url") or ""):  # samo prave web poveznice
            e["url"] = ""
        bucket.append({f: e.get(f, "") for f in ("date", "time", "title", "venue", "genre", "price", "url")})

    for e in manual:
        add(dict(e), prefer=False)
    for e in scraped:
        add(dict(e), prefer=True)

    # Podaci o izvođačima iz MusicBrainza (scrapers/enrich.py)
    artists_path = DATA / "artists.json"
    if artists_path.exists():
        from scrapers.enrich import artist_query, norm as anorm
        artists = json.loads(artists_path.read_text())
        for b in buckets.values():
            for e in b:
                a = artists.get(anorm(artist_query(e["title"])))
                if a and a.get("mbid") and a.get("links"):
                    if a.get("links"):
                        e["links"] = {k: u for k, u in a["links"].items() if re.match(r"^https?://", u or "")}
                    if a.get("genre") and e.get("genre") in ("", "ostalo", None):
                        e["genre"] = a["genre"]

    # Poveznice bendova sa stranica najava (scrapers/eventlinks.py) – dopunjuju ono što MusicBrainz nema
    ev_links_path = DATA / "eventlinks.json"
    if ev_links_path.exists():
        ev_links = json.loads(ev_links_path.read_text())
        for b in buckets.values():
            for e in b:
                extra = (ev_links.get(e.get("url") or "") or {}).get("clean") or {}
                if extra:
                    links = dict(extra)
                    links.update(e.get("links") or {})  # MusicBrainz ima prednost
                    e["links"] = {k: u for k, u in links.items() if re.match(r"^https?://", u or "")}

    events = sorted((e for b in buckets.values() for e in b), key=lambda e: (e["date"], e["time"] or "99", e["title"]))
    used = {e["venue"] for e in events} | {venues[e["venue"]].get("group") for e in events if venues[e["venue"]].get("group")}
    out_venues = {k: v for k, v in venues.items() if k in used or v.get("regular")}
    payload = {"updated": today, "site_url": SITE_URL, "venues": out_venues, "events": events}

    # Stabilan kratki ID i datum prve pojave (za RSS "novo najavljeno")
    seen_path = DATA / "seen.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    for e in events:
        e["id"] = hashlib.sha1(f"{e['date']}|{group(e['venue'])}|{norm(e['title'])}".encode()).hexdigest()[:8]
        seen.setdefault(e["id"], today)
        e["added"] = seen[e["id"]]
    seen = {k: v for k, v in seen.items() if v >= (date.today() - timedelta(days=400)).isoformat()}
    seen_path.write_text(json.dumps(seen, indent=0, sort_keys=True))

    SITE.mkdir(exist_ok=True)
    write_feeds(events, out_venues)
    html = (ROOT / "template" / "index.html").read_text()
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = re.sub(r"/\*__DATA__\*/\{.*?\};", lambda _: f"/*__DATA__*/{data_js};", html, count=1, flags=re.S)
    (SITE / "index.html").write_text(html)
    # Statične datoteke aplikacije (ikone, manifest, service worker)
    for f in (ROOT / "template" / "static").iterdir():
        data = f.read_bytes()
        if f.name == "sw.js":
            data = data.replace(b"__VERSION__", hashlib.sha1(html.encode()).hexdigest()[:10].encode())
        (SITE / f.name).write_bytes(data)
    (SITE / "events.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"{len(events)} događaja u {len(out_venues)} prostora (ručno {len(manual)}, automatski {len(scraped)})")


GENRES = {"rock": "Rock", "metal": "Metal", "punk": "Punk", "alt": "Alternativa", "pop": "Pop", "narodna": "Narodna",
          "elektro": "Elektronika", "dj": "DJ party", "hiphop": "Hip-hop", "jazz": "Jazz", "klasika": "Klasika", "trad": "Tradicijska",
          "world": "World", "djeca": "Za djecu", "ostalo": "Ostalo"}

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Zagreb
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


def ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line: str) -> str:
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > 73:
            out.append(cur.decode())
            cur = b" "
        cur += b
    out.append(cur.decode())
    return "\r\n".join(out)


def ics(events: list[dict], venues: dict, name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Koncerti u Zagrebu//HR", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{ics_escape(name)}", "X-WR-TIMEZONE:Europe/Zagreb",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"] + VTIMEZONE.split("\n")
    for e in events:
        v = venues.get(e["venue"], {})
        d = e["date"].replace("-", "")
        if e.get("time"):
            start = datetime.strptime(f"{e['date']} {e['time']}", "%Y-%m-%d %H:%M")
            end = start + timedelta(hours=3)
            when = [f"DTSTART;TZID=Europe/Zagreb:{start:%Y%m%dT%H%M%S}", f"DTEND;TZID=Europe/Zagreb:{end:%Y%m%dT%H%M%S}"]
        else:
            nxt = (datetime.strptime(e["date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
            when = [f"DTSTART;VALUE=DATE:{d}", f"DTEND;VALUE=DATE:{nxt}"]
        loc = ", ".join(x for x in [v.get("name", ""), v.get("address", ""), "Zagreb"] if x)
        desc = " · ".join(x for x in [GENRES.get(e.get("genre") or "ostalo", ""), e.get("price", ""), e.get("url", "")] if x)
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@koncerti-zagreb", f"DTSTAMP:{stamp}", *when,
                  f"SUMMARY:{ics_escape(e['title'])}", f"LOCATION:{ics_escape(loc)}",
                  f"DESCRIPTION:{ics_escape(desc)}"] + ([f"URL:{e['url']}"] if e.get("url") else []) + ["END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(l) for l in lines) + "\r\n"


def rss(events: list[dict], venues: dict, name: str) -> str:
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    items = []
    for e in sorted(events, key=lambda e: (e["added"], e["date"]), reverse=True)[:60]:
        v = venues.get(e["venue"], {}).get("name", "")
        dt = datetime.strptime(e["date"], "%Y-%m-%d")
        added = datetime.strptime(e["added"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        items.append(f"<item><title>{esc(e['title'])} – {dt.day}. {dt.month}. {dt.year}., {esc(v)}</title>"
                     f"<link>{esc(e.get('url') or '')}</link><guid isPermaLink=\"false\">{e['id']}</guid>"
                     f"<pubDate>{format_datetime(added)}</pubDate>"
                     f"<description>{esc(' · '.join(x for x in [e.get('time',''), v, e.get('price','')] if x))}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>{esc(name)}</title><link>https://branimir-max.github.io/koncerti/</link>"
            f"<description>Novo najavljeni koncerti u Zagrebu</description><language>hr</language>{''.join(items)}</channel></rss>")


def write_feeds(events: list[dict], venues: dict) -> None:
    cal, feed = SITE / "cal", SITE / "rss"
    cal.mkdir(parents=True, exist_ok=True)
    feed.mkdir(parents=True, exist_ok=True)
    grp = lambda k: venues.get(k, {}).get("group", k)  # noqa: E731
    sets = {"sve": ("Koncerti u Zagrebu", events)}
    for g, label in GENRES.items():
        sel = [e for e in events if (e.get("genre") or "ostalo") == g]
        if sel:
            sets[g] = (f"Koncerti u Zagrebu – {label}", sel)
    for k in {grp(e["venue"]) for e in events}:
        sets[f"prostor-{k}"] = (f"Koncerti – {venues.get(k, {}).get('name', k)}", [e for e in events if grp(e["venue"]) == k])
    for key, (name, sel) in sets.items():
        (cal / f"{key}.ics").write_text(ics(sel, venues, name), newline="")
        (feed / f"{key}.xml").write_text(rss(sel, venues, name))


if __name__ == "__main__":
    main()
