"""Zajednički alati za skupljače: dohvat stranice i izvlačenje događaja.

Svaki izvor vraća listu rječnika:
    {"date": "YYYY-MM-DD", "time": "HH:MM" ili "", "title": str,
     "venue": ključ iz data/venues.json, "genre": str ili "", "price": str, "url": str}
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

UA = "KoncertiZagreb/0.1 (+https://github.com/branimir-max/koncerti)"
TIMEOUT = 25

MONTHS_HR = {
    "siječnja": 1, "veljače": 2, "ožujka": 3, "travnja": 4, "svibnja": 5, "lipnja": 6,
    "srpnja": 7, "kolovoza": 8, "rujna": 9, "listopada": 10, "studenoga": 11, "studenog": 11,
    "prosinca": 12,
}


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "hr,en;q=0.8"}, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------- datumi ----------

DATE_PATTERNS = [
    # 13.11.2026. / 13. 11. 2026 / 13.11.26
    re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2}(?![:.\d]))\.?"),
    # 2026-11-13
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:h|sati)?\b")


def parse_date(text: str, today: date | None = None) -> str | None:
    """Vrati prvi datum iz teksta kao YYYY-MM-DD (podržava hrvatske formate)."""
    today = today or date.today()
    m = DATE_PATTERNS[1].search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = DATE_PATTERNS[0].search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    # 21.11. bez godine
    m = re.search(r"\b(\d{1,2})\.\s?(0?[1-9]|1[0-2])\.(?!\d)", text)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = today.year + (1 if mo < today.month - 1 else 0)
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            pass
    # "13. studenoga 2026" ili "13. studenoga"
    m = re.search(r"\b(\d{1,2})\.\s*(" + "|".join(MONTHS_HR) + r")\s*(\d{4})?", text.lower())
    if m:
        d, mo = int(m.group(1)), MONTHS_HR[m.group(2)]
        y = int(m.group(3)) if m.group(3) else (today.year + (1 if mo < today.month - 1 else 0))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def parse_time(text: str) -> str:
    # Prvo makni datume, inače bi "14.11.2026" izgledalo kao 14:11
    text = DATE_PATTERNS[0].sub(" ", DATE_PATTERNS[1].sub(" ", text))
    text = re.sub(r"\b\d{1,2}\.\s*(" + "|".join(MONTHS_HR) + r")", " ", text, flags=re.I)
    text = re.sub(r"\b\d{1,2}\.\s?(0?[1-9]|1[0-2])\.(?!\d)", " ", text)  # 21.11. bez godine
    m = re.search(r"po[čc]etak\D{0,5}([01]?\d|2[0-3])[:.]([0-5]\d)", text, re.I)  # "Početak 21:00" ima prednost pred vratima
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = TIME_RE.search(text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"\b([01]?\d|2[0-3])\s?h\b", text)
    return f"{int(m.group(1)):02d}:00" if m else ""


# ---------- JSON-LD (schema.org Event) ----------

def _iter_ld(obj):
    if isinstance(obj, list):
        for o in obj:
            yield from _iter_ld(o)
    elif isinstance(obj, dict):
        if "@graph" in obj:
            yield from _iter_ld(obj["@graph"])
        yield obj


def jsonld_events(html: str, venue: str, base_url: str, genre: str = "") -> list[dict]:
    """Izvuci događaje iz <script type="application/ld+json"> blokova."""
    out = []
    for tag in soup(html).find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for o in _iter_ld(data):
            t = o.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if not any("Event" in str(x) for x in types):
                continue
            start = str(o.get("startDate", ""))
            if not start:
                continue
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                d, tm = dt.date().isoformat(), (dt.strftime("%H:%M") if "T" in start else "")
            except ValueError:
                d, tm = parse_date(start), parse_time(start)
            if not d:
                continue
            price = ""
            offers = o.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict) and offers.get("price") not in (None, ""):
                price = f"{offers.get('price')} {offers.get('priceCurrency', '€')}".replace("EUR", "€")
            loc = o.get("location") or {}
            if isinstance(loc, list) and loc:
                loc = loc[0]
            loc_text = loc.get("name", "") if isinstance(loc, dict) else str(loc)
            out.append({
                "date": d, "time": tm, "title": clean(o.get("name", "")), "venue": venue,
                "genre": genre, "price": price, "url": o.get("url") or base_url, "_text": loc_text,
            })
    return out


# ---------- heuristika: datum + naslov u istom bloku ----------

def card_events(html: str, venue: str, base_url: str, genre: str = "",
                card_selector: str | None = None, title_selector: str = "h1, h2, h3, h4, .title, [class*=title]") -> list[dict]:
    """Za stranice bez JSON-LD: nađi blokove koji sadrže datum i naslov.

    Ako card_selector nije zadan, uzima najmanje elemente (article, li, div)
    koji sadrže točno jedan datum i jedan naslov.
    """
    s = soup(html)
    cards = s.select(card_selector) if card_selector else s.find_all(["article", "li", "div"])
    out, seen = [], set()
    for c in cards:
        text = c.get_text(" ", strip=True)
        if not card_selector and len(text) > 600:  # prevelik blok, vjerojatno cijela stranica
            continue
        d = parse_date(text)
        if not d:
            continue
        h = c.select_one(title_selector)
        title = clean(h.get_text(" ", strip=True)) if h else ""
        if not title or parse_date(title) == d and len(title) < 14:
            continue
        key = (d, title.lower())
        if key in seen:
            continue
        seen.add(key)
        a = c.find("a", href=True)
        url = requests.compat.urljoin(base_url, a["href"]) if a else base_url
        out.append({"date": d, "time": parse_time(text), "title": title, "venue": venue,
                    "genre": genre, "price": find_price(text), "url": url, "_text": text})
    return out


PRICE_RE = re.compile(r"(\d{1,3}(?:[.,]\d{2})?)\s?(?:€|eur)", re.I)


def find_price(text: str) -> str:
    if re.search(r"rasprodan", text, re.I):
        return "rasprodano"
    if re.search(r"besplatn|free entry|ulaz slobodan", text, re.I):
        return "besplatno"
    m = re.search(r"(\d{1,3}(?:[.,]\d{2})?)\s?[/–-]\s?(\d{1,3}(?:[.,]\d{2})?)\s?(?:€|eur)", text, re.I)
    prices = [m.group(1), m.group(2)] + PRICE_RE.findall(text) if m else PRICE_RE.findall(text)
    if not prices:
        return ""
    fmt = lambda v: f"{v:g}" if v.is_integer() else f"{v:.2f}".replace(".", ",")  # noqa: E731 – 40.00 -> 40, 32.9 -> 32,90
    vals = sorted({float(p.replace(",", ".")) for p in prices})
    return f"{fmt(vals[0])} €" if len(vals) == 1 else f"{fmt(vals[0])}–{fmt(vals[-1])} €"


def clean(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKC", str(s))  # npr. 𝗠𝗢𝗡𝗢𝗟𝗢𝗥𝗗 -> MONOLORD
    return re.sub(r"\s+", " ", s).strip()


# ---------- microdata (itemtype="http://schema.org/Event"), npr. KSET ----------

def microdata_events(html: str, venue: str, base_url: str) -> list[dict]:
    out = []
    for el in soup(html).select('[itemtype*="schema.org/Event"], [itemtype*="schema.org/MusicEvent"]'):
        name = el.select_one('[itemprop="name"]')
        start = el.select_one('[itemprop="startDate"]')
        if not name or not start:
            continue
        d = parse_date(start.get("datetime") or start.get("content") or start.get_text(" "))
        if not d:
            continue
        door = el.select_one('[itemprop="doorTime"]')
        tm = ""
        if door:
            t = door.get("datetime") or door.get_text(strip=True)
            tm = parse_time(t) or (f"{int(t):02d}:00" if t.isdigit() and int(t) < 24 else "")
        link = el.select_one('[itemprop="url"]') or el.find("a", href=True)
        text = el.get_text(" ", strip=True)
        out.append({"date": d, "time": tm, "title": clean(name.get_text(" ", strip=True)), "venue": venue,
                    "genre": "", "price": find_price(text),
                    "url": requests.compat.urljoin(base_url, link["href"]) if link and link.get("href") else base_url,
                    "_text": clean(name.get_text(" ", strip=True))})
    return out


# ---------- TooToot (platforma za ulaznice koju koriste Močvara i Dva Osam) ----------

def tootoot_events(html: str, venue: str, base_url: str) -> list[dict]:
    s, out = soup(html), []
    for li in s.select(".tt-evt-li"):
        name = li.select_one(".tt-evt-li__name")
        if not name:
            continue
        info = " ".join(x.get_text(" ", strip=True) for x in li.select("[class*=sub-info]") if "About" not in " ".join(x.get("class", [])))
        d = parse_date(info)
        if not d:
            continue
        a = name if name.name == "a" else name.find("a", href=True)
        out.append({"date": d, "time": parse_time(info), "title": clean(name.get_text(" ", strip=True)), "venue": venue,
                    "genre": "", "price": find_price(info), "url": a.get("href", base_url) if a else base_url, "_text": info})
    for a in s.select('a.swiper-slide-inner[href*="event-detail"]'):
        heading = a.select_one(".elementor-slide-heading")
        desc = a.select_one(".elementor-slide-description")
        d = parse_date(desc.get_text(" ", strip=True)) if desc else None
        if heading and d:
            out.append({"date": d, "time": "", "title": clean(heading.get_text(" ", strip=True)), "venue": venue,
                        "genre": "", "price": "", "url": a["href"], "_text": ""})
    return out


# ---------- stranica jednog događaja (za izvore koji na naslovnici nemaju datume) ----------

def page_event(html: str, url: str, venue: str) -> dict | None:
    found = jsonld_events(html, venue, url)
    if found:
        return found[0]
    s = soup(html)
    og = s.find("meta", property="og:title")
    h1 = s.find("h1")
    title = clean(og["content"]) if og and og.get("content") else (clean(h1.get_text(" ", strip=True)) if h1 else "")
    main = s.find("main") or s.find("article") or s.body or s
    text = main.get_text(" ", strip=True)[:3000]
    d = parse_date(text)
    if not title or not d:
        return None
    return {"date": d, "time": parse_time(text), "title": re.sub(r"\s[|–-]\s[^|–-]+$", "", title), "venue": venue,
            "genre": "", "price": find_price(text), "url": url, "_text": text[:300]}


def event_links(html: str, base_url: str, pattern: str, limit: int = 25) -> list[str]:
    links, seen = [], set()
    for a in soup(html).find_all("a", href=True):
        href = requests.compat.urljoin(base_url, a["href"]).split("#")[0]
        if re.search(pattern, href) and href not in seen and href.rstrip("/") != base_url.rstrip("/"):
            seen.add(href)
            links.append(href)
    return links[:limit]
