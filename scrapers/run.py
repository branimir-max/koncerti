"""Pokreni sve skupljače: python -m scrapers.run

Svaki izvor sprema rezultat u data/scraped/<key>.json. Ako izvor padne ili ne
vrati ništa, zadržava se prethodna datoteka (da jedan pokvaren izvor ne
izbriše podatke), a problem se zapisuje u data/report.json.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .base import hnk_events, ics_events, coreevent_events, ulaznice_events, card_events, clean, event_links, fetch, jsonld_events, microdata_events, page_event, soup, tootoot_events
from .sources import GENRE_WORDS, JUNK, SOURCES

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "scraped"
VENUES = json.loads((ROOT / "data" / "venues.json").read_text())
CITIES = json.loads((ROOT / "data" / "cities.json").read_text())


def city_of(place: str) -> str | None:
    """Grad iz teksta mjesta ('Dom mladih, Split' -> 'split')."""
    p = place.lower()
    for key, c in CITIES.items():
        if any(re.search(rf"\b{re.escape(w)}\b", p) for w in c["match"]):
            return key
    return None


def strip_city(name: str, city: str) -> str:
    words = "|".join(re.escape(w) for w in CITIES.get(city, {}).get("match", []) + [CITIES.get(city, {}).get("name", city)])
    name = re.sub(rf",\s*\b({words})\b.*$", "", name, flags=re.I).strip(" ,-")
    return name


def venue_from_text(text: str, city: str = "zagreb") -> str | None:
    """Prepoznaj prostor po nazivu u tekstu; dulji nazivi imaju prednost. Samo prostori iz tog grada."""
    t = text.lower()
    pairs = [(a.lower(), k) for k, v in VENUES.items() if "group" not in v and v.get("city", "zagreb") == city
             for a in [v.get("name", "")] + v.get("aliases", []) if a]
    for alias, key in sorted(pairs, key=lambda p: -len(p[0])):
        if alias in t:
            return key
    return None


def classify(title: str, default: str, dj_words: list[str]) -> str:
    t = f" {title.lower()} ".replace("no jazz", "")  # NO Jazz festival nije jazz
    if any(w in t for w in dj_words) or title.lower().startswith("dj "):
        return "dj"
    for genre, words in GENRE_WORDS:
        if any(w in t for w in words):
            return genre
    return default or ""


DEBUG = ROOT / "data" / "debug"


ACRONYMS = {"HRT", "HRT-A", "SO", "DJ", "KSET", "UNICEF", "USA", "UK", "II", "III", "IV", "HGM", "NYE", "XXL", "MC"}
SMALL = {"i", "u", "za", "na", "od", "do", "s", "sa", "en", "la", "de", "feat.", "ft.", "and", "of", "the", "uz", "x"}


def nice_case(t: str) -> str:
    """Naslove pisane VELIKIM SLOVIMA pretvori u normalan oblik ('LET 3 U TVORNICI' -> 'Let 3 u Tvornici')."""
    letters = [c for c in t if c.isalpha()]
    if len(letters) <= 3 or sum(c.isupper() for c in letters) / len(letters) < 0.7:
        return t
    words = []
    for i, w in enumerate(t.split()):
        core = re.sub(r"[^\w-]", "", w).upper()
        if core in ACRONYMS or any(ch.isdigit() for ch in w):
            words.append(w if core != "HRT-A" else w.replace("HRT-A", "HRT-a"))
        elif i > 0 and w.lower() in SMALL:
            words.append(w.lower())
        else:
            words.append(w[:1].upper() + w[1:].lower())
    return " ".join(words)


PROBE = ROOT / "data" / "probe"


def write_probe(key: str, html: str) -> None:
    """Kratki sažetak strukture stranice (bez skripti i ključeva) za pisanje novog parsera.
    Sprema se u repozitorij, za razliku od cijelih snimki."""
    from .base import parse_date, soup as _soup
    s = _soup(html)
    lines = [f"title: {s.title.get_text(strip=True) if s.title else ''}"]
    lines.append("jsonld types: " + ", ".join(re.findall(r'"@type"\s*:\s*"([^"]+)"', html))[:300])
    n = 0
    for el in s.find_all(["article", "li", "div", "a", "tr"]):
        t = el.get_text(" ", strip=True)
        if not t or len(t) > 220 or not parse_date(t):
            continue
        cls = ".".join(el.get("class", [])[:3])
        href = el.get("href", "") if el.name == "a" else (el.find("a", href=True) or {}).get("href", "")
        lines.append(f"<{el.name} class={cls}> {t[:200]} | {str(href)[:120]}")
        n += 1
        if n >= 60:
            break
    if n == 0:  # nijedan blok s prepoznatim datumom: pokaži općenitu strukturu
        lines.append("bez prepoznatih datuma; html bytes=%d" % len(html))
        lines.append("api/json hints: " + ", ".join(sorted(set(re.findall(r"[\"'](/[\w/.-]*(?:api|json|ajax|raspored)[\w/.?=&-]*)[\"']", html)))[:15]))
        for el in s.find_all(True, class_=True):
            t = el.get_text(" ", strip=True)
            if t and len(t) < 160 and re.search(r"\d", t) and el.name not in ("script", "style"):
                lines.append(f"<{el.name} class={'.'.join(el.get('class', [])[:3])}> {t[:150]}")
                n += 1
                if n >= 60:
                    break
    PROBE.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    text = re.sub(r"[A-Za-z0-9_\-]{32,}", "[…]", text)  # dugi nizovi (mogući ključevi) van
    (PROBE / f"{key}.txt").write_text(text)


def scrape(src: dict) -> list[dict]:
    events: list[dict] = []
    for i, url in enumerate(src["urls"]):
        try:
            html = fetch(url)
        except Exception:  # noqa: BLE001 – prva stranica mora proći, dodatne (page=2…) smiju izostati
            if i == 0 and not src.get("tolerant"):
                raise
            continue
        if i == 0:  # snimka prve stranice za otklanjanje grešaka
            DEBUG.mkdir(parents=True, exist_ok=True)
            (DEBUG / f"{src['key']}.html").write_text(html[:400_000])
            if src.get("probe"):
                write_probe(src["key"], html)
        v = src["venue"] or ""
        parser = src.get("parser")
        if parser == "tootoot":
            found = tootoot_events(html, v, url)
        elif parser in ("ulaznice", "coreevent"):
            fn = ulaznice_events if parser == "ulaznice" else coreevent_events
            found = []
            for e in fn(html, url):
                c = city_of(e["_place"])
                if c:  # samo gradovi koje pokrivamo
                    e["city"] = c
                    e["venue_name"] = strip_city(e.pop("_place"), c)
                    found.append(e)
        elif parser == "ics":
            found = []
            for e in ics_events(html, url):
                if src.get("categories") and not any(w in e["_cats"] for w in src["categories"]):
                    continue
                place = e.pop("_place")
                e.pop("_cats", None)
                e["venue_name"] = place.split(",")[0].strip()  # "Klub Palach, Kružna 8, Rijeka" -> "Klub Palach"
                found.append(e)
        elif parser == "hnk":
            found = hnk_events(html, url, v)
            for e in found:
                e.pop("_stage", None)
        elif parser == "microdata":
            found = microdata_events(html, v, url)
        elif parser == "detail":
            found = []
            for j, link in enumerate(event_links(html, url, src["link_pattern"])):
                try:
                    page = fetch(link)
                    if j == 0:
                        (DEBUG / f"{src['key']}-detail.html").write_text(page[:300_000])
                    e = page_event(page, link, v)
                    if e:
                        found.append(e)
                except Exception:  # noqa: BLE001 – jedna pokvarena stranica ne ruši izvor
                    pass
                time.sleep(1)
        elif parser == "cards":
            found = card_events(html, v, url, card_selector=src.get("card"), title_selector=src.get("title", "h1, h2, h3, h4, .title, [class*=title]"))
        else:
            found = jsonld_events(html, v, url) or card_events(html, v, url, card_selector=src.get("card"))
        # Prostor iz teksta (agregatori, KSET) ili dvorana (Lisinski)
        src_city = src.get("city", "zagreb")
        if src.get("locality"):  # Songkick: odbaci okolicu (Kranj, Šibenik, Mödling…)
            found = [e for e in found if city_of(e.get("_text", "")) == src_city]
        for e in found:
            e["city"] = e.get("city") or src_city
            blob = e.pop("_text", "") or e["title"]
            e["_blob"] = (e["title"] + " " + blob).lower()
            for hall, key in src.get("halls", {}).items():
                if hall in blob.lower():
                    e["venue"] = key
            if not src["venue"]:
                e["venue"] = venue_from_text(blob, e["city"]) or src.get("default_venue", "")
                if not e["venue"]:
                    e["venue_name"] = strip_city(e.get("venue_name") or blob[:60], e["city"])
        events += found
        time.sleep(1.5)  # pristojno prema serverima
    # Filtriranje i obogaćivanje
    out, seen = [], set()
    today = date.today().isoformat()
    for e in events:
        blob = e.pop("_blob", e["title"].lower())
        if any(w in blob for w in src.get("exclude", [])):
            continue
        if src.get("include") and not any(w in blob for w in src["include"]):
            continue
        if src.get("require") and src["require"].lower() not in blob:
            continue
        for pat in src.get("strip", []):
            e["title"] = re.sub(pat, "", e["title"], flags=re.I).strip()
        e["title"] = nice_case(clean(e["title"]))
        # ukrasi s najava: emojiji na rubovima i "… u Rijeci!" / "… u Pogonu!" na kraju
        e["title"] = re.sub(r"^[^\w\"„(]+|[^\w)\"”'’.?!]+$", "", e["title"]).strip()
        e["title"] = re.sub(r"\s+u\s+[A-ZČĆŠŽĐ][\wčćšžđ]+!$", "", e["title"]).strip()
        title_l = e["title"].lower()
        if e["date"] < today or len(title_l) < 2:
            continue
        if any(w in title_l for w in src.get("exclude", [])) or any(title_l.startswith(w) for w in JUNK):
            continue
        if any(w in (e.get("venue_name") or "").lower() for w in src.get("outside", [])):
            continue
        prefix = src.get("title_prefix", "")
        if prefix and not e["title"].upper().startswith(prefix.split(":")[0].upper()):
            e["title"] = prefix + e["title"]
        e["genre"] = src.get("force_genre") or e.get("genre") or classify(e["title"], src.get("genre", ""), src.get("dj_words", []))
        e["source"] = src["key"]
        k = (e["date"], e["title"].lower())
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


_ROBOTS: dict = {}


def robots_blocked(urls: list[str]) -> list[str]:
    """Koje adrese robots.txt stranice ne dopušta automatskom čitanju (za naš UA ili sve)."""
    from urllib.parse import urlsplit
    from urllib.robotparser import RobotFileParser
    from .base import UA
    out = []
    for u in urls:
        p = urlsplit(u)
        root = f"{p.scheme}://{p.netloc}"
        if root not in _ROBOTS:
            rp = RobotFileParser()
            try:
                txt = fetch(root + "/robots.txt")
                rp.parse(txt.splitlines())
            except Exception:  # noqa: BLE001 – bez robots.txt sve je dopušteno
                rp.parse([])
            _ROBOTS[root] = rp
        if not _ROBOTS[root].can_fetch(UA.split("/")[0], u):
            out.append(u)
    return out


def main(only: list[str] | None = None) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": {}}
    for src in SOURCES:
        if only and src["key"] not in only:
            continue
        path = OUT / f"{src['key']}.json"
        try:
            events = scrape(src)
            if events:
                path.write_text(json.dumps(events, ensure_ascii=False, indent=1))
                status = {"ok": True, "count": len(events)}
                if not src.get("debug_always"):
                    (DEBUG / f"{src['key']}.html").unlink(missing_ok=True)  # snimka treba samo kad izvor ne radi
                    (DEBUG / f"{src['key']}-detail.html").unlink(missing_ok=True)
            elif src.get("allow_empty"):
                path.write_text("[]")
                status = {"ok": True, "count": 0, "note": "trenutno nema koncerata"}
            else:
                status = {"ok": False, "count": 0, "error": "nijedan događaj nije prepoznat (promijenio se HTML?)"}
        except Exception as ex:  # noqa: BLE001 – jedan izvor ne smije srušiti ostale
            status = {"ok": False, "count": 0, "error": f"{type(ex).__name__}: {ex}"[:300]}
        try:
            blocked = robots_blocked(src["urls"])
            if blocked:
                status["robots"] = "zabranjeno: " + ", ".join(blocked)[:300]
        except Exception:  # noqa: BLE001
            pass
        report["sources"][src["key"]] = status
        print(f"{src['key']:10} {'OK ' if status['ok'] else 'ERR'} {status['count']:4}  {status.get('error', '')}")
    (ROOT / "data" / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
