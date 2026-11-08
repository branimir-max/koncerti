"""Pokreni sve skupljače: python -m scrapers.run

Svaki izvor sprema rezultat u data/scraped/<key>.json. Ako izvor padne ili ne
vrati ništa, zadržava se prethodna datoteka (da jedan pokvaren izvor ne
izbriše podatke), a problem se zapisuje u data/report.json.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .base import card_events, clean, fetch, jsonld_events, soup
from .sources import GENRE_WORDS, SOURCES

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
    if any(w in t for w in dj_words):
        return "dj"
    for genre, words in GENRE_WORDS:
        if any(w in t for w in words):
            return genre
    return default or ""


def scrape(src: dict) -> list[dict]:
    events: list[dict] = []
    for url in src["urls"]:
        html = fetch(url)
        found = jsonld_events(html, src["venue"] or "", url)
        if not found:
            found = card_events(html, src["venue"] or "", url, card_selector=src.get("card"))
        # Prostor iz teksta (agregatori, KSET) ili dvorana (Lisinski)
        for e in found:
            blob = e.pop("_text", "") or e["title"]
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
        title_l = e["title"].lower()
        if e["date"] < today:
            continue
        if any(w in title_l for w in src.get("exclude", [])):
            continue
        prefix = src.get("title_prefix", "")
        if prefix and not e["title"].startswith(prefix):
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
