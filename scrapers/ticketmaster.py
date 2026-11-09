"""Ticketmaster Discovery API – službeni, javni API (https://developer.ticketmaster.com).

Radi samo kad postoji tajna TM_API_KEY (GitHub → Settings → Secrets → Actions).
Bez ključa izvor tiho vraća prazan popis.

Uvjeti korištenja koje poštujemo:
  - svaki koncert vodi na Ticketmasterovu stranicu događaja (url iz API-ja);
  - podatke osvježavamo dnevno i ne čuvamo prošle događaje;
  - ne naplaćujemo pristup tim podacima.
Ključ se nikad ne zapisuje u datoteke ni u izvještaj (repo je javan).
"""
from __future__ import annotations

import os
import time

import requests

API = "https://app.ticketmaster.com/discovery/v2/events.json"

# Ticketmasterov žanr -> naš žanr ("" = neka odluči classify/enrich)
GENRE = {
    "rock": "rock", "metal": "metal", "punk": "punk", "alternative": "alt", "jazz": "jazz", "blues": "blues",
    "pop": "pop", "hip-hop/rap": "hiphop", "dance/electronic": "elektro", "classical": "klasika",
    "folk": "world", "world": "world", "children's music": "djeca", "r&b": "pop", "country": "rock",
}


class TMError(RuntimeError):
    pass


def events(spec: str) -> list[dict]:
    """spec = "AT/Wien" (kod države / grad kako ga piše Ticketmaster)."""
    key = os.environ.get("TM_API_KEY", "").strip()
    if not key:
        return []
    country, city = spec.split("/", 1)
    out, page = [], 0
    while page < 5:  # API ne daje dublje od 1000 rezultata (5 × 200)
        params = {"apikey": key, "countryCode": country, "city": city, "classificationName": "music",
                  "size": 200, "page": page, "sort": "date,asc", "locale": "*"}
        try:
            r = requests.get(API, params=params, timeout=30, headers={"User-Agent": "Gigomat/0.3 (+https://gigomat.com)"})
        except requests.RequestException as ex:
            raise TMError(type(ex).__name__) from None  # poruka bi sadržavala adresu s ključem
        if r.status_code != 200:
            raise TMError(f"HTTP {r.status_code}")
        data = r.json()
        for e in data.get("_embedded", {}).get("events", []):
            ev = _event(e)
            if ev:
                out.append(ev)
        pg = data.get("page", {})
        if pg.get("number", 0) + 1 >= pg.get("totalPages", 0):
            break
        page += 1
        time.sleep(0.5)  # ograničenje: 5 upita u sekundi
    return out


def _event(e: dict) -> dict | None:
    start = e.get("dates", {}).get("start", {})
    d = start.get("localDate")
    if not d or e.get("dates", {}).get("status", {}).get("code") in ("cancelled", "canceled"):
        return None
    venues = e.get("_embedded", {}).get("venues") or [{}]
    v = venues[0]
    place = v.get("name", "")
    town = (v.get("city") or {}).get("name", "")
    price = ""
    pr = e.get("priceRanges") or []
    if pr and pr[0].get("min") is not None:
        cur = pr[0].get("currency", "")
        price = f"{pr[0]['min']:g} {'€' if cur == 'EUR' else cur}".strip()
    genre = ""
    for c in e.get("classifications") or []:
        g = ((c.get("genre") or {}).get("name") or "").lower()
        if g in GENRE:
            genre = GENRE[g]
            break
    return {
        "date": d, "time": (start.get("localTime") or "")[:5], "title": e.get("name", "").strip(),
        "venue": "", "genre": genre, "price": price, "url": e.get("url", ""),
        "_text": f"{place}, {town}" if town else place,
    }
