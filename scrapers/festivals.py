"""Robot za festivale: za svaki festival iz data/festivals.json pogleda službenu stranicu
i pokuša pronaći datume sljedećeg izdanja (JSON-LD Event/Festival ili tekst tipa
"2.–5. 7. 2027." / "July 2–5, 2027"). Pronađene datume upisuje u polje "next".
Ništa ne izmišlja: ako datum nije jasno napisan, festival ostaje "datumi uskoro".
"""
from __future__ import annotations

import json
import re
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .base import UA, fetch, _iter_ld

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "festivals.json"

EN = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
HR = {"sij": 1, "velj": 2, "ožu": 3, "tra": 4, "svi": 5, "lip": 6, "srp": 7, "kol": 8, "ruj": 9, "lis": 10, "stu": 11, "pro": 12}
D = r"(\d{1,2})"
DASH = r"\s*(?:[–—\-/&]|do|to|bis)\s*"


def _ok(y: int, m: int, d1: int, d2: int) -> tuple[str, str] | None:
    try:
        a, b = date(y, m, d1), date(y, m, d2)
    except ValueError:
        return None
    if b < a or (b - a).days > 14:
        return None
    return a.isoformat(), b.isoformat()


def text_dates(text: str, years: list[int]) -> list[tuple[str, str]]:
    t = " ".join(text.split())
    out = []
    for y in years:
        # 2.–5. 7. 2027.  |  2.-5.7.2027
        for m in re.finditer(D + r"\.?" + DASH + D + r"\.\s*" + r"(\d{1,2})\.\s*" + str(y), t):
            r = _ok(y, int(m[3]), int(m[1]), int(m[2]))
            r and out.append(r)
        # 2–5 July 2027 | 2nd - 5th July 2027 | 2.–5. srpnja 2027.
        for m in re.finditer(D + r"(?:st|nd|rd|th|\.)?" + DASH + D + r"(?:st|nd|rd|th|\.)?\s+([a-zčćžšđ]{3,})\.?,?\s+" + str(y), t, re.I):
            mon = EN.get(m[3][:3].lower()) or HR.get(m[3][:3].lower()) or HR.get(m[3][:4].lower())
            if mon:
                r = _ok(y, mon, int(m[1]), int(m[2]))
                r and out.append(r)
        # July 2–5, 2027
        for m in re.finditer(r"([A-Za-z]{3,})\.?\s+" + D + r"(?:st|nd|rd|th)?" + DASH + D + r"(?:st|nd|rd|th)?,?\s+" + str(y), t):
            mon = EN.get(m[1][:3].lower())
            if mon:
                r = _ok(y, mon, int(m[2]), int(m[3]))
                r and out.append(r)
    return out


def ld_dates(html: str) -> list[tuple[str, str]]:
    out = []
    for blk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(blk)
        except ValueError:
            continue
        for o in _iter_ld(data):
            if not isinstance(o, dict):
                continue
            typ = o.get("@type")
            typ = " ".join(typ) if isinstance(typ, list) else str(typ or "")
            if "Event" in typ or "Festival" in typ:
                a, b = str(o.get("startDate", ""))[:10], str(o.get("endDate", "") or o.get("startDate", ""))[:10]
                if re.match(r"\d{4}-\d\d-\d\d$", a) and re.match(r"\d{4}-\d\d-\d\d$", b):
                    out.append((a, b))
    return out


def allowed(url: str) -> bool:
    p = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(fetch(f"{p.scheme}://{p.netloc}/robots.txt").splitlines())
    except Exception:  # nema robots.txt = dopušteno
        return True
    return rp.can_fetch(UA, url)


def main() -> int:
    data = json.loads(PATH.read_text())
    today = date.today()
    years = [today.year, today.year + 1]
    report = {}
    for f in data["festivals"]:
        url = f.get("url")
        if not url:
            report[f["key"]] = "nema službene stranice"
            continue
        try:
            if not allowed(url):
                report[f["key"]] = "robots.txt ne dopušta"
                continue
            html = fetch(url)
        except Exception as ex:  # noqa: BLE001
            report[f["key"]] = f"greška: {ex.__class__.__name__}"
            continue
        plain = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I))
        found = [r for r in ld_dates(html) + text_dates(plain, years) if r[1] >= today.isoformat()]
        if not found:
            report[f["key"]] = "datumi nisu pronađeni"
            continue
        a, b = min(found)
        if (f.get("next") or {}).get("from") != a or (f.get("next") or {}).get("to") != b:
            f["next"] = {"from": a, "to": b, "checked": today.isoformat()}
        report[f["key"]] = f"{a} – {b}"
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    (ROOT / "data" / "festivals-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    for k, v in report.items():
        print(f"{k:14} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
