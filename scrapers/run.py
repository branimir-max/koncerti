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

from .base import card_events, clean, event_links, fetch, jsonld_events, microdata_events, page_event, soup, tootoot_events
from .sources import GENRE_WORDS, JUNK, SOURCES

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "scraped"
VENUES = json.loads((ROOT / "data" / "venues.json").read_text())


def venue_from_text(text: str) -> str | None:
    """Prepoznaj prostor po nazivu u tekstu; dulji nazivi imaju prednost."""
    t = text.lower()
    pairs = [(a.lower(), k) for k, v in VENUES.items() if "group" not in v
             for a in [v.get("name", "")] + v.get("aliases", []) if a]
    for alias, key in sorted(pairs, key=lambda p: -len(p[0])):
        if alias in t:
            return key
    return None


def classify(title: str, default: str, dj_words: list[str]) -> str:
    t = f" {title.lower()} "
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


def scrape(src: dict) -> list[dict]:
    events: list[dict] = []
    for i, url in enumerate(src["urls"]):
        html = fetch(url)
        if i == 0:  # snimka prve stranice za otklanjanje grešaka
            DEBUG.mkdir(parents=True, exist_ok=True)
            (DEBUG / f"{src['key']}.html").write_text(html[:400_000])
        v = src["venue"] or ""
        parser = src.get("parser")
        if parser == "tootoot":
            found = tootoot_events(html, v, url)
        elif parser == "microdata":
            found = microdata_events(html, v, url)
        elif parser == "detail":
            found = []
            for link in event_links(html, url, src["link_pattern"]):
                try:
                    e = page_event(fetch(link), link, v)
                    if e:
                        found.append(e)
                except Exception:  # noqa: BLE001 – jedna pokvarena stranica ne ruši izvor
                    pass
                time.sleep(1)
        elif parser == "cards":
            found = card_events(html, v, url, card_selector=src.get("card"))
        else:
            found = jsonld_events(html, v, url) or card_events(html, v, url, card_selector=src.get("card"))
        # Prostor iz teksta (agregatori, KSET) ili dvorana (Lisinski)
        for e in found:
            blob = e.pop("_text", "") or e["title"]
            e["_blob"] = (e["title"] + " " + blob).lower()
            for hall, key in src.get("halls", {}).items():
                if hall in blob.lower():
                    e["venue"] = key
            if not src["venue"]:
                e["venue"] = venue_from_text(blob) or src.get("default_venue", "")
                if not e["venue"]:
                    e["venue_name"] = blob[:60]
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
        e["genre"] = e.get("genre") or classify(e["title"], src.get("genre", ""), src.get("dj_words", []))
        e["source"] = src["key"]
        k = (e["date"], e["title"].lower())
        if k not in seen:
            seen.add(k)
            out.append(e)
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
                (DEBUG / f"{src['key']}.html").unlink(missing_ok=True)  # snimka treba samo kad izvor ne radi
            else:
                status = {"ok": False, "count": 0, "error": "nijedan događaj nije prepoznat (promijenio se HTML?)"}
        except Exception as ex:  # noqa: BLE001 – jedan izvor ne smije srušiti ostale
            status = {"ok": False, "count": 0, "error": f"{type(ex).__name__}: {ex}"[:300]}
        report["sources"][src["key"]] = status
        print(f"{src['key']:10} {'OK ' if status['ok'] else 'ERR'} {status['count']:4}  {status.get('error', '')}")
    (ROOT / "data" / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
