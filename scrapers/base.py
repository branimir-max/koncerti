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

UA = "Gigomat/0.3 (+https://gigomat.com)"
TIMEOUT = 25

MONTHS_HR = {
    "siječnja": 1, "veljače": 2, "ožujka": 3, "travnja": 4, "svibnja": 5, "lipnja": 6,
    "srpnja": 7, "kolovoza": 8, "rujna": 9, "listopada": 10, "studenoga": 11, "studenog": 11,
    "prosinca": 12,
}


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "hr,en;q=0.8"}, timeout=TIMEOUT)
    r.raise_for_status()
    if "charset" not in r.headers.get("content-type", "").lower():  # bez deklaracije requests pogađa latin-1 (A38: "Ã¡")
        try:
            return r.content.decode("utf-8")
        except UnicodeDecodeError:
            r.encoding = r.apparent_encoding
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
# Mjeseci na njemačkom, mađarskom, slovenskom i engleskom (Beč, Budimpešta, Ljubljana)
MONTHS_X = {}
for _n, _words in enumerate([
        "jan januar jänner jänn january január januarja", "feb februar february február februarja",
        "mar mär märz march március márc marec marca", "apr april április aprila", "mai may máj május maj maja",
        "jun juni june jún június junij junija", "jul juli july júl július julij julija",
        "aug august augusztus avg avgust avgusta", "sep sept september szeptember szept septembra",
        "okt oct oktober october október oktobra", "nov november novembra", "dez dec dezember december decembra"], 1):
    for _w in _words.split():
        MONTHS_X[_w] = _n
_MX = "|".join(sorted(MONTHS_X, key=len, reverse=True))
_WD = r"(?:[a-zäöüáéíóöőúüűčšž]{2,4}\.?,?\s+)?"  # dan u tjednu između dana i mjeseca ("11 Mi. Nov")
DAY_MONTH_RE = re.compile(rf"\b(\d{{1,2}})\.?\s+{_WD}({_MX})\b\.?\s*(?:\|\s*)?,?\s*(\d{{4}})?", re.I)
MONTH_DAY_RE = re.compile(rf"\b({_MX})\b\.?\s+(\d{{1,2}})(?:\.(?!\d)|,?\s+(\d{{4}})\b)", re.I)  # "Nov 12." / "Nov 12, 2026"
HU_DATE_RE = re.compile(r"\b(20\d\d)\.\s?(\d{1,2})\.\s?(\d{1,2})\b")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:h|sati)?\b")


def parse_date(text: str, today: date | None = None) -> str | None:
    """Vrati prvi datum iz teksta kao YYYY-MM-DD (podržava hrvatske formate)."""
    today = today or date.today()
    m = HU_DATE_RE.search(text)  # 2026.11.21.
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
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
    # "10. November 2026", "11 Mi. Nov | 2026", "14 NOV SZO", "17. nov.", "Nov 12."
    for rx, di, mi in ((DAY_MONTH_RE, 1, 2), (MONTH_DAY_RE, 2, 1)):
        m = rx.search(text)
        if m:
            d, mo = int(m.group(di)), MONTHS_X[m.group(mi).lower()]
            y = int(m.group(3)) if m.group(3) else (today.year + (1 if mo < today.month - 1 else 0))
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                return None
    return None


def parse_time(text: str) -> str:
    # Prvo makni datume, inače bi "14.11.2026" izgledalo kao 14:11
    text = HU_DATE_RE.sub(" ", text)
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
            addr = loc.get("address") if isinstance(loc, dict) else None
            town = addr.get("addressLocality", "") if isinstance(addr, dict) else ""
            if town and town.lower() not in loc_text.lower():
                loc_text = f"{loc_text}, {town}"  # grad, da drugi gradovi mogu odvojiti okolicu
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
        a = c if c.name == "a" and c.get("href") else c.find("a", href=True)
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


# ---------- Ulaznice.hr (kategorija Glazba, cijela Hrvatska) ----------

def ulaznice_events(html: str, base_url: str) -> list[dict]:
    out = []
    for art in soup(html).select("article.happeningContainer"):
        h = art.select_one("h3.smallTitle a, h3 a")
        spans = [sp.get_text(" ", strip=True) for sp in art.select(".happeningInfoContainer p span")]
        if not h or not spans:
            continue
        place = clean(spans[0].replace("\xa0", " "))
        when = " ".join(spans[1:])
        if " - " in when:  # višemjesečne ulaznice/članstva, ne koncerti
            continue
        d = parse_date(when)
        if not d:
            continue
        text = art.get_text(" ", strip=True)
        out.append({"date": d, "time": parse_time(text), "title": clean(h.get_text(" ", strip=True)), "venue": "",
                    "genre": "", "price": find_price(text), "url": requests.compat.urljoin(base_url, h.get("href", "")),
                    "_text": place, "_place": place})
    return out


# ---------- Core Event (core-event.co) ----------

def coreevent_events(html: str, base_url: str) -> list[dict]:
    out = []
    for a in soup(html).select("a.event-card-background"):
        typ = a.select_one(".event-type")
        title = a.select_one(".event-title")
        desc = a.select_one(".event-description")
        loc = a.select_one(".event-location")
        if not title or not desc or not loc:
            continue
        if typ and typ.get_text(strip=True).lower() not in ("music", "glazba", "koncert", "party", "festival"):
            continue
        when = clean(desc.get_text(" ", strip=True))
        when = re.sub(r"(\d{1,2})\.\s*[–-]\s*\d{1,2}\.", r"\1.", when)  # "13. – 14. studenoga" -> prvi dan
        d = parse_date(when)
        if not d:
            continue
        place = clean(loc.get_text(" ", strip=True))
        out.append({"date": d, "time": parse_time(when), "title": clean(title.get_text(" ", strip=True)), "venue": "",
                    "genre": "", "price": "", "url": clean(a.get("href", base_url)),
                    "_text": place, "_place": place})
    return out


# ---------- iCalendar (npr. visitrijeka.hr, WordPress "The Events Calendar") ----------

def ics_events(text: str, base_url: str) -> list[dict]:
    """Događaji iz .ics datoteke; _place = LOCATION, _cats = CATEGORIES."""
    text = re.sub(r"\r?\n[ \t]", "", text)  # spoji presavijene retke
    out = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.S):
        f = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            f[k.split(";")[0].upper()] = v.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").strip()
        start = f.get("DTSTART", "")
        m = re.match(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?", start)
        if not m or not f.get("SUMMARY"):
            continue
        d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        tm = f"{m.group(4)}:{m.group(5)}" if m.group(4) and f"{m.group(4)}{m.group(5)}" != "0000" else ""
        place = f.get("LOCATION", "")
        out.append({"date": d, "time": tm, "title": clean(f["SUMMARY"]), "venue": "", "genre": "", "price": "",
                    "url": f.get("URL") or base_url, "_text": place, "_place": place, "_cats": f.get("CATEGORIES", "").lower()})
    return out


# ---------- HNK Zagreb (raspored: blokovi div.item s "Uto 10" bez mjeseca) ----------

HR_DOW = {"pon": 0, "uto": 1, "sri": 2, "čet": 3, "cet": 3, "pet": 4, "sub": 5, "ned": 6}


def hnk_events(html: str, base_url: str, venue: str) -> list[dict]:
    """Raspored HNK-a ima samo dan u tjednu i broj dana; mjesec se izvodi redoslijedom
    (prvi sljedeći datum s tim brojem dana koji pada na taj dan u tjednu)."""
    from datetime import date as _d, timedelta as _td
    s = soup(html)
    out, cur = [], _d.today()
    for item in s.select("div.item"):
        h = item.select_one(".date")
        if not h:
            continue
        m = re.match(r"\s*(\w{3})\w*\s+(\d{1,2})", h.get_text(" ", strip=True).lower())
        if not m or m.group(1) not in HR_DOW:
            continue
        dow, day = HR_DOW[m.group(1)], int(m.group(2))
        found = None
        for k in range(0, 400):
            c = cur + _td(days=k)
            if c.day == day and c.weekday() == dow:
                found = c
                break
        if not found:
            continue
        cur = found
        text = item.get_text(" ", strip=True)
        if "gostovanje" in text.lower():   # izvedba izvan HNK-a
            continue
        t = item.select_one("h3") or item.select_one("h2") or item.select_one(".title")
        title = clean(t.get_text(" ", strip=True)) if t else ""
        title = re.split(r"\s+Izvedba se održava", title)[0]
        if not title:
            continue
        stage = "HNK2" if "HNK2" in text else ""
        a = item.find("a", href=True)
        out.append({"date": found.isoformat(), "time": parse_time(text), "title": title, "venue": venue,
                    "genre": "", "price": "", "url": requests.compat.urljoin(base_url, a["href"]) if a else base_url,
                    "_text": text, "_stage": stage})
    return out


def row_events(html: str, venue: str, base_url: str, row: str, link: str, require: str = "") -> list[dict]:
    """Tablični program (Kino Šiška): svaki redak ima datum, vrijeme, kategoriju i poveznicu na događaj."""
    out = []
    for r in soup(html).select(row):
        text = r.get_text(" ", strip=True)
        if require and require.lower() not in text.lower():
            continue
        d = parse_date(text)
        links = [a for a in r.find_all("a", href=True) if link in a["href"]]
        if not d or not links:
            continue
        names = [clean(a.get_text(" ", strip=True)) for a in links]
        names = [n for n in names if n and not re.search(r"nakup|vstopnic|tickets?|kupi", n, re.I)]
        if not names:
            continue
        out.append({"date": d, "time": parse_time(text), "title": max(names, key=len), "venue": venue, "genre": "",
                    "price": find_price(text), "url": requests.compat.urljoin(base_url, links[0]["href"]), "_text": text})
    return out
