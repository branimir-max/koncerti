"""Obogati izvođače podacima iz MusicBrainza: python -m scrapers.enrich

Za svakog izvođača traži točan pogodak u MusicBrainzu (besplatna otvorena baza)
i sprema službene poveznice (web, Spotify, YouTube, Instagram…) i žanrove u
data/artists.json. Rezultati (i promašaji) se pamte, pa se svaki izvođač
provjerava samo jednom (promašaji ponovo nakon 60 dana).

MusicBrainz traži najviše 1 upit u sekundi i opisan User-Agent.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "artists.json"
UA = "KoncertiZagreb/0.2 ( https://github.com/branimir-max/koncerti )"
API = "https://musicbrainz.org/ws/2"
EXYU = {"HR", "RS", "BA", "SI", "ME", "MK", "XK", "YU"}
MAX_LOOKUPS = 400  # po pokretanju, da prvi put ne traje predugo

SERIES = r"^(kset\d*|lisinski (subotom|srijedom|da camera)[^:]*|majstorski ciklus[^:]*|[^:]{0,40}(festival|ciklus|party|večer|sezona)[^:]*):\s*"
SKIP = re.compile(r"filharmonij|simfonij|orkestar|kvartet|zbor|ciklus|koncert u povodu|smotr|festival|dječj|"
                  r"glazbena priča|tribute|party|afterparty|gala|obljetnic|božić|bal\b|natjecanj", re.I)

# MusicBrainz žanr/oznaka -> naš žanr (prvi pogodak pobjeđuje)
GENRE_MAP = [
    ("metal", "metal"), ("punk", "punk"), ("hardcore", "punk"), ("hip hop", "hiphop"), ("hip-hop", "hiphop"),
    ("rap", "hiphop"), ("trap", "hiphop"), ("jazz", "jazz"), ("classical", "klasika"), ("opera", "klasika"),
    ("techno", "elektro"), ("house", "elektro"), ("electronic", "elektro"), ("ambient", "elektro"),
    ("drum and bass", "elektro"), ("synth", "alt"), ("post-punk", "alt"), ("indie", "alt"), ("alternative", "alt"),
    ("shoegaze", "alt"), ("darkwave", "alt"), ("experimental", "alt"), ("folk", "world"), ("world", "world"),
    ("reggae", "world"), ("blues", "rock"), ("rock", "rock"), ("pop", "pop"), ("schlager", "narodna"),
    ("turbo-folk", "narodna"), ("singer-songwriter", "pop"), ("soul", "pop"), ("funk", "pop"),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"['’`]", "", s)  # Mother’s = Mothers
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def artist_query(title: str) -> str:
    q = re.sub(SERIES, "", title, flags=re.I)
    q = re.split(r"\s[–-]\s|\s\+\s|,|\(|\s@\s|\sx\s|\sfeat\.?\s|\sft\.?\s|:|\s&\s(?=[A-ZČĆŠŽĐ])|/", q, flags=re.I)[0]
    return re.sub(r"[\"„“”]", "", q).strip()


def get(url: str, params: dict) -> dict:
    for attempt in range(3):
        r = requests.get(url, params={**params, "fmt": "json"}, headers={"User-Agent": UA}, timeout=20)
        time.sleep(1.1)
        if r.status_code == 503:  # preopterećeno – pričekaj i probaj ponovo
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    return {}


def pick(results: list[dict], q: str) -> dict | None:
    nq = norm(q)
    strip_the = lambda n: re.sub(r"^the ", "", n)  # noqa: E731
    exact = [a for a in results if a.get("score", 0) >= 90 and strip_the(norm(a.get("name", ""))) == strip_the(nq)]
    if not exact:
        return None
    if len(exact) == 1:
        return exact[0]
    exyu = [a for a in exact if a.get("country") in EXYU or (a.get("area") or {}).get("iso-3166-1-codes", [None])[0] in EXYU]
    if len(exyu) == 1:
        return exyu[0]
    # više istoimenih izvođača bez jasnog izbora: radije ništa nego krivi bend
    return None


def links_of(rels: list[dict]) -> dict:
    out = {}
    for rel in rels:
        url = (rel.get("url") or {}).get("resource", "")
        t = rel.get("type", "")
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        key = None
        if "spotify.com" in host:
            key = "spotify"
        elif "deezer.com" in host:
            key = "deezer"
        elif "youtube.com" in host or "youtu.be" in host:
            key = "youtube"
        elif "bandcamp.com" in host:
            key = "bandcamp"
        elif "soundcloud.com" in host:
            key = "soundcloud"
        elif "instagram.com" in host:
            key = "instagram"
        elif "facebook.com" in host:
            key = "facebook"
        elif t == "official homepage":
            key = "web"
        if key and key not in out:
            out[key] = url
    return out


def genre_of(data: dict) -> str:
    tags = sorted((data.get("genres") or []) + (data.get("tags") or []), key=lambda t: -t.get("count", 0))
    for t in tags:
        name = t.get("name", "").lower()
        for word, g in GENRE_MAP:
            if word in name:
                return g
    return ""


def main() -> int:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    events = json.loads((ROOT / "site" / "events.json").read_text())["events"] if (ROOT / "site" / "events.json").exists() else []
    queries = []
    for e in events:
        q = artist_query(e["title"])
        if len(q) < 2 or SKIP.search(e["title"]) or e.get("genre") in ("klasika", "djeca"):
            continue
        queries.append(q)
    stale = (date.today() - timedelta(days=60)).isoformat()
    todo = [q for q in dict.fromkeys(queries) if norm(q) not in cache or
            (not cache[norm(q)].get("mbid") and cache[norm(q)].get("checked", "") < stale)]
    print(f"{len(set(queries))} izvođača, {len(todo)} za provjeru")
    hits = 0
    for q in todo[:MAX_LOOKUPS]:
        entry = {"query": q, "checked": date.today().isoformat()}
        try:
            res = get(f"{API}/artist/", {"query": f'artist:"{q}" OR alias:"{q}"', "limit": 8}).get("artists", [])
            a = pick(res, q)
            if a:
                full = get(f"{API}/artist/{a['id']}", {"inc": "url-rels+genres+tags"})
                entry.update({"mbid": a["id"], "name": a.get("name"), "country": a.get("country", ""),
                              "links": links_of(full.get("relations", [])), "genre": genre_of(full)})
                hits += 1
        except requests.RequestException as ex:
            print("  greška:", q, ex)
            continue
        cache[norm(q)] = entry
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
    print(f"pronađeno {hits} novih izvođača; u bazi {sum(1 for v in cache.values() if v.get('mbid'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
