"""Spoji ručne i automatski skupljene podatke i izgradi stranicu: python build.py

Ulaz:  data/venues.json, data/manual.json, data/scraped/*.json
Izlaz: site/index.html (aplikacija s ugrađenim podacima), site/events.json
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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
        bucket.append({f: e.get(f, "") for f in ("date", "time", "title", "venue", "genre", "price", "url")})

    for e in manual:
        add(dict(e), prefer=False)
    for e in scraped:
        add(dict(e), prefer=True)

    events = sorted((e for b in buckets.values() for e in b), key=lambda e: (e["date"], e["time"] or "99", e["title"]))
    used = {e["venue"] for e in events} | {venues[e["venue"]].get("group") for e in events if venues[e["venue"]].get("group")}
    out_venues = {k: v for k, v in venues.items() if k in used}
    payload = {"updated": today, "venues": out_venues, "events": events}

    SITE.mkdir(exist_ok=True)
    html = (ROOT / "template" / "index.html").read_text()
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = re.sub(r"/\*__DATA__\*/\{.*?\};", lambda _: f"/*__DATA__*/{data_js};", html, count=1, flags=re.S)
    (SITE / "index.html").write_text(html)
    (SITE / "events.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"{len(events)} događaja u {len(out_venues)} prostora (ručno {len(manual)}, automatski {len(scraped)})")


if __name__ == "__main__":
    main()
