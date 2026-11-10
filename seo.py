"""Stranice za tražilice: koncert (/k/<id>/), prostor (/prostori/<slug>/), žanr (/zanr/<žanr>/),
i karta stranica (samo Zagreb; stranice koncerata iz drugih gradova postoje za dijeljenje, ali su noindex) (sitemap.xml).

Svaka stranica je obična HTML stranica u izgledu Gigomata, s pravim sadržajem (bez preusmjeravanja),
da je Google može pročitati. Stranica koncerta ima strukturirane podatke (schema.org MusicEvent),
pa koncert može ući u Googleov popis događaja.
"""
from __future__ import annotations

import html as H
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Zagreb")
DAYS = ["ponedjeljak", "utorak", "srijeda", "četvrtak", "petak", "subota", "nedjelja"]
MONTHS = ["siječnja", "veljače", "ožujka", "travnja", "svibnja", "lipnja", "srpnja", "kolovoza", "rujna",
          "listopada", "studenoga", "prosinca"]
COUNTRY = {"ljubljana": "SI", "maribor": "SI", "bec": "AT", "budimpesta": "HU"}
# "Metal koncerti u Zagrebu" – oblik naziva žanra za naslov stranice
GENRE_T = {"rock": "Rock koncerti", "metal": "Metal koncerti", "punk": "Punk koncerti", "alt": "Alternativni koncerti",
           "jazz": "Jazz koncerti", "blues": "Blues koncerti", "pop": "Pop koncerti", "hiphop": "Hip-hop i rap koncerti",
           "elektro": "Elektronička glazba", "dj": "DJ partyji", "klasika": "Koncerti klasične glazbe",
           "opera": "Opera i balet", "world": "World glazba", "trad": "Tradicijska glazba",
           "narodna": "Narodna glazba", "djeca": "Koncerti za djecu"}

e_ = lambda s: H.escape(str(s or ""), quote=True)  # noqa: E731


def slugify(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def when(e: dict) -> str:
    d = date.fromisoformat(e["date"])
    return f"{DAYS[d.weekday()]}, {d.day}. {MONTHS[d.month - 1]} {d.year}." + (f" u {e['time']}" if e.get("time") else "")


def short(e: dict) -> str:
    d = date.fromisoformat(e["date"])
    return f"{DAYS[d.weekday()][:3]} {d.day}.{d.month}."


def page(title: str, desc: str, canon: str, body: str, root: str, extra_head: str = "", noindex: bool = False) -> str:
    return f"""<!doctype html>
<html lang="hr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e_(title)}</title>
<meta name="description" content="{e_(desc)}">
<link rel="canonical" href="{canon}">{'<meta name="robots" content="noindex">' if noindex else ''}
<meta property="og:type" content="website"><meta property="og:site_name" content="Gigomat">
<meta property="og:title" content="{e_(title)}"><meta property="og:description" content="{e_(desc)}">
<meta property="og:url" content="{canon}"><meta property="og:image" content="{root}icon-512.png">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#121212">
<link rel="icon" type="image/png" sizes="32x32" href="{root}favicon-32.png">
<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<link rel="stylesheet" href="{root}fonts.css"><link rel="stylesheet" href="{root}page.css">
<style>
.crumbs{{font-family:var(--font-mono,monospace);font-size:12px;margin:14px 0 4px}}
.crumbs a{{color:inherit}}
h1{{margin:6px 0 4px}}
.when{{font-family:"Big Shoulders Display",sans-serif;font-weight:800;font-size:30px;line-height:1;text-transform:uppercase;margin:8px 0 2px}}
.where{{font-family:"IBM Plex Mono",monospace;font-size:14px;margin:0 0 14px}}
.where a{{color:inherit}}
.acts{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 22px}}
.acts a{{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 14px;border:2px solid var(--ink);color:var(--ink);text-decoration:none;font-weight:700;background:var(--surface)}}
.acts a.pri{{background:#121212;color:#E9E4D8;border-color:#121212}}
.facts{{border-top:2px solid var(--ink);margin:0;padding:0}}
.facts div{{display:grid;grid-template-columns:110px 1fr;gap:10px;padding:9px 0;border-bottom:1px dashed var(--ink)}}
.facts dt{{font-family:"IBM Plex Mono",monospace;font-size:12px;text-transform:uppercase;padding-top:2px}}
.facts dd{{margin:0}}
.list{{list-style:none;margin:8px 0 24px;padding:0}}
.list li{{display:grid;grid-template-columns:84px 1fr;gap:10px;align-items:baseline;padding:10px 0;border-bottom:1px dashed var(--ink)}}
.list .d{{font-family:"IBM Plex Mono",monospace;font-size:12.5px}}
.list a{{color:var(--ink);font-weight:700;text-decoration:none}}
.list a:hover{{text-decoration:underline}}
.list small{{display:block;font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:400;margin-top:2px}}
h2{{font-family:"Big Shoulders Display",sans-serif;font-weight:800;text-transform:uppercase;font-size:24px;margin:22px 0 0}}
.tags{{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 20px;padding:0;list-style:none}}
.tags a{{display:inline-block;border:2px solid var(--ink);padding:4px 9px;color:var(--ink);text-decoration:none;font-size:14px}}
</style>{extra_head}
</head><body>
<header class="band"><div class="bandin"><a class="logo" href="{root}" aria-label="Gigomat, početna"><span class="dot" aria-hidden="true"></span>gigomat</a></div></header>
<main class="wrap">
{body}
<p class="crumbs"><a href="{root}">Svi koncerti</a> · <a href="{root}prijavi.html">Prijavi događaj</a> · <a href="{root}privatnost.html">Privatnost</a></p>
</main></body></html>"""


def ev_li(e: dict, venues: dict, root: str, show_venue: bool = True) -> str:
    v = venues.get(e["venue"], {})
    sub = " · ".join(x for x in [e.get("time", ""), v.get("name", "") if show_venue else "", ] if x)
    return (f'<li><span class="d">{short(e)}</span><span><a href="{root}k/{e["id"]}/">{e_(e["title"])}</a>'
            f'{f"<small>{e_(sub)}</small>" if sub else ""}</span></li>')


def jsonld(e: dict, v: dict, city: dict, site: str) -> str:
    start = e["date"]
    if e.get("time") and re.match(r"^\d{1,2}:\d{2}$", e["time"]):
        h, m = map(int, e["time"].split(":"))
        start = datetime.fromisoformat(e["date"]).replace(hour=h, minute=m, tzinfo=TZ).isoformat()
    place = {"@type": "Place", "name": v.get("full") or v.get("name", ""),
             "address": {"@type": "PostalAddress", "streetAddress": v.get("address", ""),
                         "addressLocality": city.get("name", ""), "addressCountry": COUNTRY.get(v.get("city"), "HR")}}
    d = {"@context": "https://schema.org", "@type": "MusicEvent", "name": e["title"], "startDate": start,
         "eventStatus": "https://schema.org/EventScheduled",
         "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
         "location": place, "url": f"{site}k/{e['id']}/", "image": [f"{site}icon-512.png"],
         "description": f"{e['title']} – {when(e)}, {v.get('name', '')}, {city.get('name', '')}.",
         "performer": {"@type": "PerformingGroup", "name": e["title"]}}
    if e.get("url"):
        offer = {"@type": "Offer", "url": e["url"]}
        if e.get("sold"):
            offer["availability"] = "https://schema.org/SoldOut"
        d["offers"] = offer
    return '<script type="application/ld+json">' + json.dumps(d, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def build(site_dir: Path, site: str, events: list[dict], venues: dict, cities: dict, genres: dict) -> int:
    """Napiši sve SEO stranice i sitemap.xml. Vraća broj stranica."""
    urls: list[str] = [site]
    today = date.today().isoformat()
    events = [e for e in events if e["date"] >= today]
    by_venue: dict[str, list[dict]] = {}
    for e in events:
        by_venue.setdefault(e["venue"], []).append(e)
    # slugovi prostora: po imenu, a ako se ime ponavlja, dodaj grad
    vslug: dict[str, str] = {}
    used: set[str] = set()
    for k in sorted(by_venue):
        v = venues.get(k, {})
        if not v or v.get("city", "zagreb") != "zagreb":
            continue
        s = slugify(v.get("name", k))
        if s in used:
            s = slugify(f"{v.get('name', k)} {v.get('city', '')}")
        if s in used:
            s = slugify(k)
        used.add(s)
        vslug[k] = s

    # --- koncerti ---
    kroot = site_dir / "k"
    kroot.mkdir(exist_ok=True)
    for e in events:
        v = venues.get(e["venue"], {})
        c = cities.get(v.get("city", e.get("city", "zagreb")), {})
        r = "../../"
        vname = v.get("name", "")
        title = f"{e['title']} · {vname}, {c.get('name', '')} · {short(e).split(' ', 1)[1]}"
        desc = f"{e['title']} – {when(e)}, {vname}, {c.get('name', '')}. Ulaznice, karta i dodavanje u kalendar na Gigomatu."
        maps = "https://www.google.com/maps/search/?api=1&query=" + re.sub(r"\s+", "+", f"{v.get('full') or vname} {v.get('address', '')} {c.get('name', '')}".strip())
        vweb = v.get("web")
        gcal = ("https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + re.sub(r"\s", "+", e_(e["title"]))
                + "&dates=" + e["date"].replace("-", "") + "/" + e["date"].replace("-", "")
                + "&location=" + re.sub(r"\s", "+", e_(f"{vname}, {c.get('name', '')}")))
        if e.get("time") and re.match(r"^\d{1,2}:\d{2}$", e["time"]):
            h, m = map(int, e["time"].split(":"))
            st = datetime.fromisoformat(e["date"]).replace(hour=h, minute=m, tzinfo=TZ)
            gcal = gcal.split("&dates=")[0] + f"&dates={st.strftime('%Y%m%dT%H%M00')}/{st.replace(hour=min(h + 3, 23)).strftime('%Y%m%dT%H%M00')}&ctz=Europe/Zagreb" + "&location=" + gcal.split("&location=")[1]
        facts = [("Kada", when(e)),
                 ("Gdje", (f'<a href="{r}prostori/{vslug[e["venue"]]}/">{e_(v.get("full") or vname)}</a>' if e["venue"] in vslug else e_(v.get("full") or vname))
                          + (f", {e_(v['address'])}" if v.get("address") else "") + f", {e_(c.get('name', ''))}"
                          + f' · <a href="{e_(maps)}" rel="nofollow">karta</a>'),
                 ]
        if e.get("genre") in genres and e.get("genre") != "ostalo":
            facts.append(("Žanr", f'<a href="{r}zanr/{e["genre"]}/">{e_(genres[e["genre"]])}</a>' if v.get("city", "zagreb") == "zagreb" else e_(genres[e["genre"]])))
        if e.get("price") or e.get("sold") or e.get("free"):
            facts.append(("Ulaz", "rasprodano" if e.get("sold") else "besplatno" if e.get("free") else e_(e["price"])))
        if e.get("url"):
            dom = re.sub(r"^https?://(www\.)?", "", e["url"]).split("/")[0]
            facts.append(("Izvor", f'<a href="{e_(e["url"])}" rel="nofollow noopener" target="_blank">{e_(dom)}</a>'))
        if vweb:
            facts.append(("Prostor", f'<a href="{e_(vweb)}" rel="nofollow noopener" target="_blank">{e_(re.sub(r"^https?://(www[.])?", "", vweb).rstrip("/"))}</a>'))
        more = [x for x in by_venue.get(e["venue"], []) if x["id"] != e["id"]][:6]
        city_link = f"{r}?grad={v.get('city', 'zagreb')}" if v.get("city", "zagreb") != "zagreb" else r
        body = f"""<p class="crumbs"><a href="{city_link}">Koncerti {e_(c.get('in', ''))}</a>{f' › <a href="{r}prostori/{vslug[e["venue"]]}/">{e_(vname)}</a>' if e["venue"] in vslug else ''}</p>
<h1>{e_(e['title'])}</h1>
<p class="when">{e_(when(e))}</p>
<p class="where">{e_(vname)}, {e_(c.get('name', ''))}</p>
<div class="acts"><a class="pri" href="{r}?k={e['id']}">★ Spremi u Gigomat</a><a href="{e_(gcal)}" rel="nofollow noopener" target="_blank">+ Google kalendar</a>{f'<a href="{e_(e["url"])}" rel="nofollow noopener" target="_blank">Ulaznice i info ↗</a>' if e.get('url') else ''}</div>
<dl class="facts">{''.join(f'<div><dt>{a}</dt><dd>{b}</dd></div>' for a, b in facts)}</dl>
{f'<h2>Još u: {e_(vname)}</h2><ul class="list">' + ''.join(ev_li(x, venues, r, False) for x in more) + '</ul>' if more else ''}
<p><a href="{city_link}">Svi koncerti {e_(c.get('in', ''))} →</a></p>"""
        (kroot / e["id"]).mkdir(exist_ok=True)
        zgb = v.get("city", "zagreb") == "zagreb"
        (kroot / e["id"] / "index.html").write_text(page(f"{title} – Gigomat", desc, f"{site}k/{e['id']}/", body, r,
                                                          jsonld(e, v, c, site) if zgb else "", noindex=not zgb))
        if zgb:
            urls.append(f"{site}k/{e['id']}/")

    # --- prostori ---
    proot = site_dir / "prostori"
    proot.mkdir(exist_ok=True)
    idx_items = []
    for k, evs in by_venue.items():
        v = venues.get(k, {})
        c = cities.get(v.get("city", "zagreb"), {})
        if k not in vslug or not evs:
            continue
        r = "../../"
        name = v.get("full") or v.get("name", k)
        title = f"{v.get('name', k)} – program koncerata · {c.get('name', '')} · Gigomat"
        desc = (f"Svi nadolazeći koncerti u prostoru {v.get('name', k)} ({c.get('name', '')}): {len(evs)} "
                f"{'koncert' if len(evs) % 10 == 1 and len(evs) % 100 != 11 else 'koncerata'}, s datumima i ulaznicama. Osvježeno svaki dan.")
        body = f"""<p class="crumbs"><a href="{r}">Gigomat</a> › <a href="{r}prostori/">Prostori</a></p>
<h1>{e_(v.get('name', k))}</h1>
<p class="where">{e_(name if name != v.get('name') else '')}{', ' if name != v.get('name') else ''}{e_(v.get('address', ''))}{', ' if v.get('address') else ''}{e_(c.get('name', ''))}{f' · <a href="{e_(v["web"])}" rel="nofollow noopener" target="_blank">službeni web</a>' if v.get('web') else ''}</p>
<h2>Nadolazeći koncerti</h2><ul class="list">{''.join(ev_li(x, venues, r, False) for x in evs[:120])}</ul>"""
        (proot / vslug[k]).mkdir(exist_ok=True)
        (proot / vslug[k] / "index.html").write_text(page(title, desc, f"{site}prostori/{vslug[k]}/", body, r))
        urls.append(f"{site}prostori/{vslug[k]}/")
        idx_items.append((c.get("name", ""), v.get("name", k), vslug[k], len(evs), v.get("city", "zagreb")))
    idx_items.sort(key=lambda x: (x[4] != "zagreb", x[0], x[1].lower()))
    groups: dict[str, list] = {}
    for it in idx_items:
        groups.setdefault(it[0], []).append(it)
    body = '<p class="crumbs"><a href="../">Gigomat</a></p><h1>Prostori u Zagrebu</h1>' + "".join(
        '<ul class="tags">' + "".join(f'<li><a href="{s}/">{e_(n)}</a></li>' for _, n, s, _, _ in its) + "</ul>"
        for cn, its in groups.items())
    (proot / "index.html").write_text(page("Koncertni prostori u Zagrebu – programi · Gigomat",
                                           "Programi koncerata po prostorima: Lisinski, Tvornica kulture, Močvara, Boogaloo, Arena i drugi.",
                                           f"{site}prostori/", body, "../"))
    urls.append(f"{site}prostori/")

    # --- žanrovi (Zagreb) ---
    zroot = site_dir / "zanr"
    zroot.mkdir(exist_ok=True)
    zg = [e for e in events if venues.get(e["venue"], {}).get("city", e.get("city")) == "zagreb"]
    for g, gt in GENRE_T.items():
        evs = [e for e in zg if e.get("genre") == g]
        if len(evs) < 2:
            continue
        r = "../../"
        title = f"{gt} u Zagrebu – svi datumi · Gigomat"
        desc = f"{gt} u Zagrebu: {len(evs)} nadolazećih događaja u Močvari, Tvornici kulture, Boogaloou, Lisinskom i drugdje. Osvježeno svaki dan."
        body = f"""<p class="crumbs"><a href="{r}">Gigomat</a> › Žanrovi</p>
<h1>{e_(gt)} u Zagrebu</h1>
<ul class="list">{''.join(ev_li(x, venues, r) for x in evs[:150])}</ul>
<h2>Ostali žanrovi</h2><ul class="tags">{''.join(f'<li><a href="{r}zanr/{k}/">{e_(t)}</a></li>' for k, t in GENRE_T.items() if k != g and sum(1 for e in zg if e.get('genre') == k) >= 2)}</ul>"""
        (zroot / g).mkdir(exist_ok=True)
        (zroot / g / "index.html").write_text(page(title, desc, f"{site}zanr/{g}/", body, r))
        urls.append(f"{site}zanr/{g}/")

    (site_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"<url><loc>{u}</loc></url>" for u in urls) + "\n</urlset>\n")
    return len(urls), vslug


def home_links(events: list[dict], venues: dict, vslug: dict) -> str:
    """Poveznice s naslovnice (vidljive i tražilicama): prostori i žanrovi u Zagrebu."""
    today = date.today().isoformat()
    zg = [e for e in events if e["date"] >= today and venues.get(e["venue"], {}).get("city", e.get("city")) == "zagreb"]
    cnt: dict[str, int] = {}
    for e in zg:
        cnt[e["venue"]] = cnt.get(e["venue"], 0) + 1
    top = [k for k in sorted(cnt, key=lambda k: -cnt[k]) if k in vslug][:16]
    gs = [g for g in GENRE_T if sum(1 for e in zg if e.get("genre") == g) >= 2]
    return ('<nav class="seolinks" aria-label="Prostori i žanrovi"><p><b>Prostori:</b> '
            + " · ".join(f'<a href="prostori/{vslug[k]}/">{e_(venues[k].get("name", k))}</a>' for k in top if k in venues)
            + ' · <a href="prostori/">svi prostori</a></p><p><b>Žanrovi:</b> '
            + " · ".join(f'<a href="zanr/{g}/">{e_(GENRE_T[g])}</a>' for g in gs) + "</p></nav>")
