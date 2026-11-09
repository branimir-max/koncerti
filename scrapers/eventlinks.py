"""Poveznice izvođača sa stranica najava: python -m scrapers.eventlinks

Mali domaći bendovi često nisu u MusicBrainzu, ali njihova najava na stranici
kluba (Močvara, Vintage, Dva Osam, Lisinski…) obično ima poveznice na Bandcamp,
Instagram, Spotify ili YouTube benda. Ovdje se te poveznice skupljaju, a
poveznice samog kluba (koje se ponavljaju na svim najavama) izbacuju.
Svaka stranica se posjećuje samo jednom (data/eventlinks.json).
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "eventlinks.json"
UA = "Gigomat/0.3 (+https://gigomat.com)"
MAX_FETCH = 250
# Agregatori i prodaja ulaznica nemaju korisne poveznice bendova
SKIP_HOSTS = ("songkick.com", "ulaznice.hr", "entrio.hr", "eventim", "karlobag.eu")


def classify(url: str) -> str | None:
    u = urlparse(url)
    host, path = u.netloc.lower().removeprefix("www.").removeprefix("m."), u.path.rstrip("/")
    if not path or path == "/":
        return None
    if host == "open.spotify.com" and re.match(r"^/(intl-\w+/)?artist/", path):
        return "spotify"
    if host.endswith(".bandcamp.com") and host != "daily.bandcamp.com":
        return "bandcamp"
    if host == "soundcloud.com" and path.count("/") == 1:
        return "soundcloud"
    if host in ("youtube.com", "youtu.be") and re.match(r"^/(@|channel/|c/|user/)", path):
        return "youtube"
    if host == "instagram.com" and path.count("/") == 1 and not re.search(r"/(p|reel|explore|stories)\b", path):
        return "instagram"
    if host == "facebook.com" and path.count("/") == 1 and not re.search(r"sharer|events|groups|profile\.php|dialog", path):
        return "facebook"
    if host == "deezer.com" and "/artist/" in path:
        return "deezer"
    return None


def page_links(html: str) -> dict:
    out: dict[str, str] = {}
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = a["href"].split("?")[0]
        k = classify(href)
        if k and k not in out:
            out[k] = href
    return out


def main() -> int:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    events = json.loads((ROOT / "site" / "events.json").read_text())["events"]
    urls = [e["url"] for e in events if e.get("url", "").startswith("http")
            and not any(h in e["url"] for h in SKIP_HOSTS) and urlparse(e["url"]).path.strip("/")]
    todo = [u for u in dict.fromkeys(urls) if u not in cache][:MAX_FETCH]
    print(f"{len(set(urls))} stranica najava, {len(todo)} novih")
    for u in todo:
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=20)
            cache[u] = {"links": page_links(r.text) if r.ok else {}, "checked": date.today().isoformat()}
        except requests.RequestException:
            cache[u] = {"links": {}, "checked": date.today().isoformat()}
        time.sleep(1)
    # Poveznice koje se pojavljuju na 3+ najave istog prostora su poveznice prostora, ne benda
    per_host = defaultdict(Counter)
    for u, v in cache.items():
        for link in set(v.get("links", {}).values()):
            per_host[urlparse(u).netloc][link] += 1
    for u, v in cache.items():
        common = {l for l, n in per_host[urlparse(u).netloc].items() if n >= 3}
        v["clean"] = {k: l for k, l in v.get("links", {}).items() if l not in common}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
    print("najava s poveznicama bendova:", sum(1 for v in cache.values() if v.get("clean")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
