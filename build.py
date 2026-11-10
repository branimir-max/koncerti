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
SITE_URL = "https://gigomat.com/"
DATA = ROOT / "data"
SITE = ROOT / "site"
CITIES = json.loads((DATA / "cities.json").read_text())


NOT_MUSIC = re.compile(r"\b(HK|KK|NK|RK|ACH)\s+\w+.*\s[–-]\s|\bvolley|hokej|košark|nogomet|rokomet|"
                       r"paketna vstopnica|paket dveh tekem|\btekm[ae]\b", re.I)


def generic_url(u: str) -> bool:
    from urllib.parse import urlparse
    p = urlparse(u)
    return "/metro-areas/" in u or (p.path.strip("/") in ("", "hr", "en") and not p.query) or p.path.rstrip("/").endswith("/dogadanja")


def trust(source: str) -> int:
    """Pouzdanost izvora: službeni program prostora > prodaja ulaznica > Songkick (agregator)."""
    if source.startswith("songkick"):
        return 1
    if source in ("ulaznice", "coreevent", "entrio", "eventim", "visitrijeka") or source.startswith(("ulaznice", "coreevent", "entrio", "ticketmaster")):
        return 2
    return 3


NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
             "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
             "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20"}
# riječi koje se ponavljaju u naslovima različitih koncerata, pa same ne znače da je koncert isti
GENERIC = set("""koncert koncerti festival festivala tribute party afterparty obljetnica obljetnice obljetnicu ansambl
ansambla orkestar orkestra zbor zbora lisinski subotom srijedom nedjeljom sezona sezone ciklus ciklusa glazbena prica djecu
band bend night live special guests gosti gost zagreb zagrebu croatia hrvatska tour edition edicija dvorana velika mala
presents predstavlja povodu svecani godisnji koncertna koncertne majstorski simfonijski jazz rock metal punk balkan
christmas bozicni bozic novogodisnji klapa klape tamburasi""".split())


# tribute bendovi i tematske DJ večeri ("Lady Gaga - Mother Monster All Night", "ABBA tribute")
COVER_NIGHT = re.compile(r"tribute|all[- ]night|\bhits night\b|sing-?along|karaoke|\bnight of\b|\bnoć\b|\bvečer\b", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^kset\d*:\s*", "", s)
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in {"the", "i", "and", "feat", "ft", "koncert", "live"}]
    return " ".join(words[:3])


def norm_all(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s.lower().replace("ı", "i").replace("ø", "o").replace("đ", "d"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^kset\d*:\s*", "", s)
    stop = {"the", "i", "and", "feat", "ft", "koncert", "live", "u", "na", "x", "presents"}
    return [NUM_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", s) if w not in stop]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm(s).replace(" ", ""))[:20] or "prostor"


def _compact(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().replace("ø", "o").replace("đ", "d"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)))


def trust_links(title: str, links: dict) -> dict:
    """Poveznice s najave vrijede samo ako su sigurno od izvođača iz naslova.
    Kod više izvođača na najavi profil mora imenom odgovarati nekom od njih,
    a Spotify/Deezer (samo brojčani ID) prihvaćamo samo za jednog izvođača."""
    names = [n for n in (_compact(x) for x in re.split(r"[,&+/:–—|]| x | feat\.? | ft\.? | i | and ", title, flags=re.I)) if len(n) >= 3]
    single = len(names) <= 1
    out = {}
    for k, u in links.items():
        m = re.match(r"https?://([^/]+)/?([^/?#]*)", u or "")
        if not m:
            continue
        host, seg = m.group(1).lower(), m.group(2)
        handle = host.split(".")[0] if host.endswith("bandcamp.com") else seg.lstrip("@")
        handle = _compact(handle)
        id_only = k in ("spotify", "deezer") or seg in ("channel", "c", "user") or handle.isdigit()
        if id_only:
            if single:
                out[k] = u
            continue
        if single or any(len(handle) >= 4 and (handle in n or n in handle) for n in names):
            out[k] = f"https://{host}/" if k == "bandcamp" else u
    return out


def main() -> None:
    venues = json.loads((DATA / "venues.json").read_text())
    for v in venues.values():
        v.setdefault("city", "zagreb")
    manual = json.loads((DATA / "manual.json").read_text())["events"]
    scraped = []
    for f in sorted((DATA / "scraped").glob("*.json")):
        for e in json.loads(f.read_text()):
            e["_t"] = trust(f.stem)
            scraped.append(e)
    scraped.sort(key=lambda e: -e["_t"])  # najpouzdaniji izvor prvi: njegov naziv i prostor ostaju

    group = lambda k: venues.get(k, {}).get("group", k)  # noqa: E731
    today = date.today().isoformat()
    buckets: dict[tuple, list[dict]] = {}

    def core(t: str) -> str:
        """Bez naziva ciklusa ispred dvotočke ("NO Jazz: Spike Fuck" -> "Spike Fuck")."""
        m = re.match(r"^([^:]{2,45}):\s*(.+)$", t)
        return m.group(2) if m else t

    def same(a: str, b: str) -> bool:
        ca, cb = core(a), core(b)
        return _same(a, b) or _same(ca, cb) or _same(ca, b) or _same(a, cb) or _same_set(a, b)

    def close_times(x: dict, y: dict) -> bool:
        if not x.get("time") or not y.get("time"):
            return True
        h = lambda t: int(t[:2]) * 60 + int(t[3:5])  # noqa: E731
        return abs(h(x["time"]) - h(y["time"])) <= 120

    def shares_name(a: str, b: str, venue: str) -> bool:
        """Isti prostor i dan: dijele li naslovi rijetku riječ (ime izvođača), npr. 'Ansambl Cantus –
        25. obljetnica' i 'Lisinski subotom: Koncert u povodu 25. obljetnice Cantus Ansambla'."""
        skip = GENERIC | set(norm_all(venues.get(venue, {}).get("name", "")))
        wa = {w for w in norm_all(core(a)) if len(w) >= 5 and w not in skip}
        wb = {w for w in norm_all(core(b)) if len(w) >= 5 and w not in skip}
        return bool(wa & wb)

    def strong(a: str, b: str) -> bool:
        """Gotovo isti naslov (za isti dan u istom gradu, a različitom prostoru)."""
        x, y = "".join(norm_all(core(a))), "".join(norm_all(core(b)))
        return len(x) >= 5 and x == y

    def _same_set(a: str, b: str) -> bool:
        sa, sb = set(norm_all(a)), set(norm_all(b))
        return bool(sa and sb) and (sa <= sb or sb <= sa)

    def _same(a: str, b: str) -> bool:
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
        if e.get("genre") == "jazz" and "no jazz" in e["title"].lower() and "jazz" not in e["title"].lower().replace("no jazz", ""):
            e["genre"] = ""  # "NO Jazz" je naziv festivala, ne žanr
        if not e.get("genre") and re.search(r"all[- ]night|\bparty\b|\bhits\b", e["title"], re.I):
            e["genre"] = "dj"  # npr. "Lady Gaga - Mother Monster All Night" je DJ večer, ne koncert
        if NOT_MUSIC.search(e["title"]):  # sportske utakmice s prodaje ulaznica (npr. dvorana Tivoli)
            return
        if e["date"] > (date.today() + timedelta(days=550)).isoformat():  # očito krivi datumi (npr. 2030.)
            return
        if not e.get("venue") or e["venue"] not in venues:
            name = e.get("venue_name") or e.get("venue") or ""
            if not name:
                return
            city = e.get("city") or "zagreb"
            known = next((k for k, v in venues.items() if v.get("city", "zagreb") == city and
                          name.strip().lower() in [a.lower() for a in v.get("aliases", [])]), None)
            if known:
                e["venue"] = known
        if not e.get("venue") or e["venue"] not in venues:
            pfx = CITIES.get(city, {}).get("pfx", "")
            key = f"{pfx}-{slug(name)}" if pfx else slug(name)
            venues.setdefault(key, {"name": name.strip(), "address": "", "auto": True, "city": city})
            e["venue"] = key
        bucket = buckets.setdefault((e["date"], group(e["venue"])), [])
        t_new = e.get("_t", 4)  # ručni unosi su najpouzdaniji
        city = venues[e["venue"]].get("city", "zagreb")
        match = next((o for o in bucket if close_times(o, e) and
                      (same(o["title"], e["title"]) or shares_name(o["title"], e["title"], e["venue"]))), None)
        if match is None:  # isti koncert, a izvori ga stavljaju u različite prostore istog grada
            for (d, g), b in buckets.items():
                if d == e["date"] and b is not bucket and b and venues[b[0]["venue"]].get("city", "zagreb") == city:
                    match = next((o for o in b if strong(o["title"], e["title"])), None)
                    if match:
                        break
        for old in ([match] if match else []):
            if True:
                # drugi nazivi istog koncerta (druga postava na drugom izvoru) – za pretragu
                if not set(norm_all(e["title"])) <= set(norm_all(old["title"])) and e["title"] not in old.setdefault("alt", []):
                    old["alt"].append(e["title"])
                # čišći naslov (bez naziva ciklusa ispred dvotočke) bolje pokazuje izvođača
                prefix = old["title"][: len(old["title"]) - len(core(old["title"]))].rstrip(": ")
                if old.get("_t") != 4 and prefix and core(e["title"]) == e["title"] \
                        and not set(norm_all(prefix)) <= set(norm_all(e["title"])):
                    old.setdefault("alt", []).append(old["title"])
                    old["title"] = e["title"]
                    old["alt"] = [a for a in old["alt"] if a != e["title"]]
                # pouzdaniji izvor odlučuje o prostoru (npr. prodaja ulaznica naspram Songkicka)
                if t_new > old.get("_t", 0) and group(e["venue"]) != group(old["venue"]) \
                        and venues[e["venue"]].get("city", "zagreb") == venues[old["venue"]].get("city", "zagreb"):
                    old["venue"] = e["venue"]
                if prefer:  # automatski podaci su svježiji, ali ne brišu poznate vrijednosti
                    better = t_new >= old.get("_t", 0) or (old.get("_t", 0) == 4 and t_new >= 2)  # Songkick samo dopunjuje
                    for f in ("time", "price", "url"):
                        if f == "url" and old.get("url") and generic_url(e.get("url") or ""):
                            continue  # ne mijenjaj poveznicu na koncert općom stranicom (popis grada, naslovnica)
                        empty = not old.get(f) or (f == "url" and generic_url(old["url"]))
                        if e.get(f) and (better or empty):
                            old[f] = e[f]
                    if not old.get("genre") and e.get("genre"):  # ručno odabrani žanr ima prednost
                        old["genre"] = e["genre"]
                    # Konkretna dvorana (npr. Lisinski – Mala dvorana) ima prednost pred općim prostorom
                    if venues.get(e["venue"], {}).get("group") and group(e["venue"]) == group(old["venue"]):
                        old["venue"] = e["venue"]
                return
        if not re.match(r"^https?://", e.get("url") or ""):  # samo prave web poveznice
            e["url"] = ""
        bucket.append({f: e.get(f, "") for f in ("date", "time", "title", "venue", "genre", "price", "url")} | {"alt": [], "_t": t_new})

    for e in manual:
        # ručni unosi prepisani sa Songkicka nisu pouzdaniji od samog Songkicka
        add(dict(e) | {"_t": 1 if "songkick.com" in (e.get("url") or "") else 4}, prefer=False)
    for e in scraped:
        add(dict(e), prefer=True)

    # Podaci o izvođačima iz MusicBrainza (scrapers/enrich.py)
    artists_path = DATA / "artists.json"
    if artists_path.exists():
        from scrapers.enrich import artist_query, norm as anorm
        artists = json.loads(artists_path.read_text())
        for b in buckets.values():
            for e in b:
                cover = COVER_NIGHT.search(e["title"])  # tribute ili tematska večer: žanr da, poveznice ne
                a = artists.get(anorm(artist_query(e["title"])))
                if a and a.get("mbid") and a.get("links"):
                    if a.get("links") and not cover:
                        e["links"] = {k: u for k, u in a["links"].items() if re.match(r"^https?://", u or "")}
                    if a.get("genre") and e.get("genre") in ("", "ostalo", None):
                        e["genre"] = a["genre"]

    # Poveznice bendova sa stranica najava (scrapers/eventlinks.py) – dopunjuju ono što MusicBrainz nema
    ev_links_path = DATA / "eventlinks.json"
    if ev_links_path.exists():
        ev_links = json.loads(ev_links_path.read_text())
        for b in buckets.values():
            for e in b:
                if COVER_NIGHT.search(e["title"]):
                    continue
                extra = trust_links(e["title"], (ev_links.get(e.get("url") or "") or {}).get("clean") or {})
                if extra:
                    links = dict(extra)
                    links.update(e.get("links") or {})  # MusicBrainz ima prednost
                    e["links"] = {k: u for k, u in links.items() if re.match(r"^https?://", u or "")}

    events = sorted((e for b in buckets.values() for e in b), key=lambda e: (e["date"], e["time"] or "99", e["title"]))
    for e in events:
        e.pop("_t", None)
    used = {e["venue"] for e in events} | {venues[e["venue"]].get("group") for e in events if venues[e["venue"]].get("group")}
    out_venues = {k: dict(v) for k, v in venues.items() if k in used or v.get("regular")}
    # Na stranicu ide samo provjerena adresa ("addr_ok"): kriva adresa može nekoga poslati na krivo mjesto
    for v in out_venues.values():
        if not v.get("addr_ok"):
            v["address"] = ""
    # Službena stranica prostora: ručno upisana ("web") ili adresa izvora koji skuplja njegov program
    from urllib.parse import urlparse
    from scrapers.sources import SOURCES
    for src in SOURCES:
        if src.get("venue") or src.get("default_venue"):
            k = src.get("venue") or src.get("default_venue")
            u = urlparse(src["urls"][0])
            for vk, v in out_venues.items():
                if (vk == k or v.get("group") == k) and not v.get("web"):
                    v["web"] = f"{u.scheme}://{u.netloc}/"
    for e in events:
        e["city"] = venues[e["venue"]].get("city", "zagreb")
    used_cities = {e["city"] for e in events} | {"zagreb"}
    out_cities = {k: {"name": c["name"], "in": c["in"]} for k, c in CITIES.items() if k in used_cities}
    out_cities = {k: {"name": c["name"], "in": c["in"], "lat": c.get("lat"), "lon": c.get("lon")} for k, c in CITIES.items() if k in used_cities}
    festivals = build_festivals(events, today)
    payload = {"updated": today, "site_url": SITE_URL, "cities": out_cities, "venues": out_venues, "events": events,
               "festivals": festivals}

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
    (SITE / "cal" / "festivali.ics").write_text(festivals_ics(festivals), newline="")
    html = (ROOT / "template" / "index.html").read_text()
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = re.sub(r"/\*__DATA__\*/\{.*?\};", lambda _: f"/*__DATA__*/{data_js};", html, count=1, flags=re.S)
    (SITE / "index.html").write_text(html)
    # Statične datoteke aplikacije (ikone, manifest, service worker)
    static = ROOT / "template" / "static"
    for f in static.rglob("*"):
        if f.is_dir():
            continue
        data = f.read_bytes()
        if f.name == "sw.js":
            data = data.replace(b"__VERSION__", hashlib.sha1(html.encode()).hexdigest()[:10].encode())
        dest = SITE / f.relative_to(static)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    (SITE / "events.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    import seo
    n_pages, vslug = seo.build(SITE, SITE_URL, events, out_venues, CITIES, GENRES)
    (SITE / "index.html").write_text((SITE / "index.html").read_text().replace("<!--SEO_LINKS-->", seo.home_links(events, out_venues, vslug)))
    print(f"SEO: {n_pages} stranica u sitemap.xml")
    print(f"{len(events)} događaja u {len(out_venues)} prostora (ručno {len(manual)}, automatski {len(scraped)})")


GENRES = {"rock": "Rock", "metal": "Metal", "punk": "Punk", "alt": "Alternativa", "jazz": "Jazz", "blues": "Blues",
          "pop": "Pop", "hiphop": "Hip-hop / rap", "elektro": "Elektronika", "dj": "DJ party", "klasika": "Klasika",
          "opera": "Opera i balet", "world": "World", "trad": "Tradicijska", "narodna": "Narodna", "djeca": "Za djecu",
          "ostalo": "Ostalo"}

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
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Gigomat//HR", "CALSCALE:GREGORIAN",
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
        loc = ", ".join(x for x in [v.get("name", ""), v.get("address", ""), CITIES.get(v.get("city", "zagreb"), {}).get("name", "")] if x)
        desc = " · ".join(x for x in [GENRES.get(e.get("genre") or "ostalo", ""), e.get("price", ""), e.get("url", "")] if x)
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@koncerti-zagreb", f"DTSTAMP:{stamp}", *when,
                  f"SUMMARY:{ics_escape(e['title'])}", f"LOCATION:{ics_escape(loc)}",
                  f"DESCRIPTION:{ics_escape(desc)}"] + ([f"URL:{e['url']}"] if e.get("url") else []) + ["END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(l) for l in lines) + "\r\n"


def rss(events: list[dict], venues: dict, name: str, city_in: str = "u Zagrebu") -> str:
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
            f"<title>{esc(name)}</title><link>{SITE_URL}</link>"
            f"<description>Novo najavljeni koncerti {esc(city_in)}</description><language>hr</language>{''.join(items)}</channel></rss>")


DAYS_HR = ["ponedjeljak", "utorak", "srijeda", "četvrtak", "petak", "subota", "nedjelja"]
MONTHS_HR = ["siječnja", "veljače", "ožujka", "travnja", "svibnja", "lipnja", "srpnja", "kolovoza", "rujna",
             "listopada", "studenoga", "prosinca"]


def write_event_pages(events: list[dict], venues: dict) -> None:
    """Mala stranica po koncertu (gigomat.com/k/<id>/) da link poslan na WhatsApp ima naslov i opis,
    a otvaranje vodi na Gigomat s tim koncertom."""
    import html as H
    root = SITE / "k"
    root.mkdir(exist_ok=True)
    for e in events:
        d = date.fromisoformat(e["date"])
        v = venues.get(e["venue"], {})
        city = CITIES.get(v.get("city", "zagreb"), {}).get("name", "")
        when = f"{DAYS_HR[d.weekday()]} {d.day}. {MONTHS_HR[d.month - 1]}" + (f" u {e['time']}" if e.get("time") else "")
        title = H.escape(f"{e['title']} · {v.get('name', '')}")
        desc = H.escape(f"{when.capitalize()} · {city}. Gigomat – koncerti u tvom gradu.")
        target = f"../../?k={e['id']}"
        page = f"""<!doctype html><html lang="hr"><head><meta charset="utf-8">
<title>{title} – Gigomat</title><meta name="viewport" content="width=device-width,initial-scale=1">
<meta property="og:type" content="website"><meta property="og:site_name" content="Gigomat">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{SITE_URL}k/{e['id']}/"><meta property="og:image" content="{SITE_URL}icon-512.png">
<meta name="twitter:card" content="summary"><meta name="description" content="{desc}">
<link rel="canonical" href="{SITE_URL}?k={e['id']}"><meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0;url={target}"></head>
<body><p><a href="{target}">{title}</a></p><script>location.replace("{target}")</script></body></html>"""
        (root / e["id"]).mkdir(exist_ok=True)
        (root / e["id"] / "index.html").write_text(page)


def km(a: dict, b: dict) -> float:
    import math
    if a.get("lat") is None or b.get("lat") is None:
        return 9999
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b["lon"] - a["lon"]) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def build_festivals(events: list[dict], today: str) -> list[dict]:
    """Festivali iz data/festivals.json. Datumi sljedećeg izdanja: potvrđeni ("next", ručno ili
    od robota scrapers/festivals.py), inače iz skupljenih koncerata čiji naslov sadrži ime festivala."""
    path = DATA / "festivals.json"
    if not path.exists():
        return []
    out = []
    for f in json.loads(path.read_text())["festivals"]:
        nxt = f.get("next") or {}
        dates = (nxt["from"], nxt["to"]) if nxt.get("to", "") >= today else None
        if not dates:
            key = " ".join(w for w in norm_all(f["name"]) if w not in {"festival", "fest", "croatia"})
            hits = sorted(e["date"] for e in events if len(key) >= 5 and e["date"] >= today
                          and km(CITIES[e["city"]], f) <= 60 and f" {key} " in " " + " ".join(norm_all(e["title"])) + " ")
            if hits and (date.fromisoformat(hits[-1]) - date.fromisoformat(hits[0])).days <= 14:
                dates = (hits[0], hits[-1])
        last = f.get("last") or {}
        out.append({"key": f["key"], "name": f["name"], "place": f["place"], "city": f.get("city", ""),
                    "lat": f["lat"], "lon": f["lon"], "url": f.get("url", ""), "genre": f.get("genre", "ostalo"),
                    "from": dates[0] if dates else "", "to": dates[1] if dates else "",
                    "last": [last["from"], last["to"]] if last.get("from") and last["to"] < today else None})
    return out


def festivals_ics(festivals: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Gigomat//HR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:Festivali u Hrvatskoj", "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for f in festivals:
        if not f["from"]:
            continue
        end = (date.fromisoformat(f["to"]) + timedelta(days=1)).strftime("%Y%m%d")
        lines += ["BEGIN:VEVENT", f"UID:fest-{f['key']}-{f['from'][:4]}@gigomat.com", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{f['from'].replace('-', '')}", f"DTEND;VALUE=DATE:{end}",
                  f"SUMMARY:{ics_escape(f['name'])}", f"LOCATION:{ics_escape(f['place'])}",
                  f"DESCRIPTION:{ics_escape(GENRES.get(f['genre'], ''))}"] + ([f"URL:{f['url']}"] if f["url"] else []) + ["END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(l) for l in lines) + "\r\n"


def write_feeds(events: list[dict], venues: dict) -> None:
    """Kalendari i RSS po gradu: Zagreb zadržava stare nazive (sve.ics, rock.ics…) da
    postojeće pretplate rade, a drugi gradovi dobiju prefiks (ljubljana-sve.ics…)."""
    cal, feed = SITE / "cal", SITE / "rss"
    cal.mkdir(parents=True, exist_ok=True)
    feed.mkdir(parents=True, exist_ok=True)
    grp = lambda k: venues.get(k, {}).get("group", k)  # noqa: E731
    sets = {}
    for city in {e["city"] for e in events}:
        c = CITIES[city]
        pre = "" if city == "zagreb" else f"{city}-"
        mine = [e for e in events if e["city"] == city]
        sets[f"{pre}sve"] = (f"Koncerti {c['in']}", mine, c["in"])
        for g, label in GENRES.items():
            sel = [e for e in mine if (e.get("genre") or "ostalo") == g]
            if sel:
                sets[f"{pre}{g}"] = (f"Koncerti {c['in']} – {label}", sel, c["in"])
    for k in {grp(e["venue"]) for e in events}:
        sel = [e for e in events if grp(e["venue"]) == k]
        sets[f"prostor-{k}"] = (f"Koncerti – {venues.get(k, {}).get('name', k)}", sel, CITIES[sel[0]["city"]]["in"])
    for key, (name, sel, city_in) in sets.items():
        (cal / f"{key}.ics").write_text(ics(sel, venues, name), newline="")
        (feed / f"{key}.xml").write_text(rss(sel, venues, name, city_in))


if __name__ == "__main__":
    main()
