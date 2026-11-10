"""Popis izvora. Novi prostor = novi unos ovdje (i po potrebi u data/venues.json).

Polja:
  key        – kratko ime izvora (ime datoteke u data/scraped/)
  urls       – stranice s programom
  venue      – ključ prostora; None ako izvor pokriva više prostora (tada se prostor
               prepoznaje iz teksta događaja ili iz JSON-LD lokacije)
  genre      – zadani žanr ako ga ne prepoznamo iz naslova
  card       – CSS selektor kartice događaja (neobavezno; bez njega radi heuristika)
  exclude    – riječi zbog kojih se događaj preskače (kazalište, predavanja…)
  dj_words   – riječi po kojima je događaj DJ party
"""

THEATRE = ["predstava", "komedija", "mjuzikl", "balet", "teorija glazbe", "predavanje",
           "radionica", "filmsk", "projekcij", "izložba", "kviz", "poezij"]
JUNK = ["blog", "intervju", "izdvojeno", "vijesti", "novosti", "newsletter", "galerija", "o nama", "kontakt"]
# Gradovi izvan Zagreba koje agregatori ponekad uvrste u "Zagreb i okolica"
OUTSIDE = ["čakovec", "cakovec", "zabok", "regenerator", "karlovac", "mala scena", "varaždin",
           "varazdin", "ljubljana", "slovenia", "samobor", "velika gorica", "sisak"]
DJ = ["party", "afterparty", "after party", "sound system", "hi-fi", "rave", "techno night"]

from datetime import date as _date
_t = _date.today()
_MONTHS = [f"{_t.year + (_t.month - 1 + i) // 12}-{(_t.month - 1 + i) % 12 + 1:02d}" for i in range(3)]

SOURCES = [
    {"key": "lisinski", "venue": "lisinski", "exclude": THEATRE + ["teatar", "aplauz", "mare #", "idea, obrt"],
     "card": "tr", "parser": "cards",
     "urls": [f"https://www.lisinski.hr/hr/dogadanja/?page={i}" for i in range(1, 6)],
     "halls": {"velika dvorana": "lisV", "mala dvorana": "lisM"}},
    {"key": "tvornica", "venue": "tvornica", "exclude": THEATRE,
     "strip": [r"\s+u\s+tvornici\s+kulture!?$"],
     "urls": ["https://www.tvornicakulture.com/", "https://www.tvornicakulture.com/svi-dogadaji/"]},
    {"key": "mocvara", "venue": "mocvara", "exclude": THEATRE, "dj_words": DJ, "parser": "tootoot",
     "strip": [r"^[^:]{3,70}:\s+(?=\S)"],
     "urls": ["https://www.mochvara.hr/"]},
    {"key": "dvaosam", "venue": "dvaosam", "exclude": THEATRE, "dj_words": DJ, "parser": "tootoot",
     "urls": ["https://dvaosam.com/"]},
    {"key": "kset", "venue": None, "exclude": THEATRE, "dj_words": DJ, "title_prefix": "KSET: ",
     "parser": "microdata", "strip": [r"\s+@\s+.*$"],
     "default_venue": "kset", "urls": ["https://www.kset.org/"]},
    {"key": "attack", "venue": "medika", "exclude": THEATRE, "dj_words": DJ,
     "urls": ["https://attack.hr/"]},
    # Boogaloo: robots.txt zabranjuje robote – samo uz njihovo dopuštenje (poslan upit).
    {"key": "vintage", "venue": "vintage", "dj_words": DJ,
     "urls": ["https://vintageindustrial-bar.com/"]},
    # Peti Kupe: na stranicama događaja nema pouzdanog datuma – pokriva ga Ulaznice.hr.
    {"key": "pogon", "venue": "pogon", "include": ["koncert", "concert"], "exclude": THEATRE, "allow_empty": True,
     "parser": "cards", "card": ".item-card", "title": ".event-title",
     "urls": ["https://www.pogon.hr/program/"]},
    # Ulaznice.hr: cijela Hrvatska na jednoj stranici – uzimamo samo Zagreb, prostor iz teksta
    {"key": "ulaznice", "venue": None, "parser": "ulaznice",
     "strip": [r"\s*@.*$", r"\s*/\s*\d{1,2}\.\d{1,2}\.\d{4}\.?$", r"\s*[-–]\s*\d{1,2}\.\s?\d{1,2}\.(\s?\d{4}\.?)?$",
               r"\s+u\s+tvornici\s+kulture!?$"], "exclude": THEATRE + ["kazalište", "konferencij", "masterclass"],
     "dj_words": DJ, "urls": ["https://www.ulaznice.hr/web/category/1"]},
    # Core Event: prodaja ulaznica za mnoge klubove (Vintage, Sax, Tvornica…); samo kategorija Music, samo Zagreb
    # (Entrio blokira automatske posjete, pa njegove koncerte hvatamo preko Ulaznice.hr)
    {"key": "coreevent", "venue": None, "parser": "coreevent", "exclude": THEATRE, "dj_words": DJ,
     "strip": [r"\s+u\s+tvornici\s+kulture!?$", r"\s*@.*$", r"\s*[-–|]\s*\d{1,2}\.\s?\d{1,2}\.(\s?\d{4}\.?)?$"],
     "urls": ["https://core-event.co/"]},
    # Songkick NE koristimo za hrvatske gradove: to je agregator, a nemamo njegovo dopuštenje.
    # Arena Zagreb i Boogaloo zabranjuju robote u robots.txt – njih dodajemo tek uz njihovo dopuštenje.
    # Ticketmaster Discovery: službeni API, radi tek kad je postavljen ključ TM_API_KEY.
    *[{"key": f"ticketmaster-{city}", "city": city, "venue": None, "parser": "ticketmaster", "locality": True,
       "allow_empty": True, "exclude": THEATRE, "dj_words": DJ, "urls": [spec]}
      for city, spec in [("zagreb", "HR/Zagreb"), ("ljubljana", "SI/Ljubljana"),
                         ("budimpesta", "HU/Budapest"), ("bec", "AT/Wien")]],

    # ---------- Drugi gradovi ----------
    # Split, Rijeka i Zabok stižu preko Ulaznice.hr i Core Eventa (gore) i Visit Rijeke.
    # Songkick se NE koristi nigdje: agregator, bez dopuštenja.
    # Kalendar Turističke zajednice Rijeke: mjesečni iCal po kategoriji; glazbu biramo po riječima i klubovima
    # HNK Zagreb: samo glazbeni program (drama ne ide u Gigomat)
    {"key": "hnk-opera", "venue": "hnk", "parser": "hnk", "force_genre": "opera", "probe": True, "allow_empty": True,
     "urls": ["https://www.hnk.hr/hr/raspored/opera/", "https://www.hnk.hr/hr/raspored/balet/"]},
    {"key": "hnk-koncert", "venue": "hnk", "parser": "hnk", "genre": "klasika", "probe": True, "allow_empty": True,
     "urls": ["https://www.hnk.hr/hr/raspored/koncert/"]},
    {"key": "visitrijeka", "city": "rijeka", "venue": None, "parser": "ics", "tolerant": True,
     "include": ["koncert", "concert", "festival", "band", "dj", "jazz", "rock", "punk", "metal", "live", "glazb", "music",
                 "orkest", "orchestra", "zbor", "choir", "klapa", "palach", "marganovo"],
     "exclude": ["izložb", "exhibition", "predstava", "radionic", "workshop", "predavanj", "lecture", "film"],
     "urls": [f"https://visitrijeka.hr/en/events/categoria/{cat}/{_m}/?ical=1"
              for _m in _MONTHS for cat in ("culture-art", "entertainment")]},
    # ---------- Službeni programi klubova: Beč, Budimpešta, Ljubljana (robots.txt provjeren) ----------
    *[dict({"city": city, "exclude": THEATRE, "dj_words": DJ, "probe": True, "allow_empty": True}, **x) for city, x in [
        ("bec", {"key": "wi-arena", "venue": "wi-arenawien", "urls": ["https://arena.wien/Home/Programm"]}),
        ("bec", {"key": "wi-flex", "venue": "wi-flex", "urls": ["https://flex.at/events/"]}),
        ("bec", {"key": "wi-planet", "venue": None, "probe_only": True, "urls": ["https://planet.tt/"]}),  # Gasometer, Szene, Simm City
        ("bec", {"key": "wi-stadthalle", "venue": "wi-stadthalle", "parser": "rows", "row": "li.event-item",
                 "link": "/events/alle-events/", "strip": [r"^(Nähere Infos zu|Detailinfos zu)\s+", r"\s+(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),.*$"],
                 "exclude": THEATRE + ["verschoben", "abgesagt", "musical", "on ice", "eisshow", "show", "comedy", "kabarett",
                                       "tennis", "handball", "basketball", "volleyball", "sport", "zirkus", "circus",
                                       "lesung", "messe", "kongress", "ballett", "nussknacker", "weihnachtspostamt"],
                 "urls": ["https://www.stadthalle.com/de/schauen/events"]}),
        ("bec", {"key": "wi-wuk", "venue": "wi-werkstattenkulturhau", "urls": ["https://www.wuk.at/musik/"]}),
        ("bec", {"key": "wi-porgy", "venue": "wi-porgybess", "genre": "jazz", "urls": ["https://www.porgy.at/events/upcoming"]}),
        ("budimpesta", {"key": "bp-akvarium", "venue": "bp-akvariumklub", "parser": "cards", "card": "a.m-card",
                        "title": "[class*=title], [class*=description], h2, h3",
                        "exclude": THEATRE + ["talks", "sicc production", "telex after", "előadás"],
                        "urls": ["https://akvariumklub.hu/programok/"]}),
        ("budimpesta", {"key": "bp-budapestpark", "venue": "bp-budapestpark", "parser": "cards", "card": "li.splide__slide",
                        "title": ".splide__slide__short", "no_time": True, "strip": [r"\s*\d{4}\.\s*\S+\s+\d{1,2}\.?$"],
                        "urls": ["https://www.budapestpark.hu/programok"]}),
        ("budimpesta", {"key": "bp-barbanegra", "venue": "bp-barbanegra", "urls": ["https://www.barbanegra.hu/programok"]}),
        ("budimpesta", {"key": "bp-a38", "venue": "bp-a38shipa38", "urls": ["https://www.a38.hu/en/programs"]}),
        ("ljubljana", {"key": "lj-festival", "venue": None, "require_venue": True, "include": ["glasb"],
                       "urls": ["https://www.ljubljanafestival.si/sl/koledar-dogodkov/"]}),
        ("ljubljana", {"key": "lj-cd", "venue": "lj-cankarjev", "url_include": "/glasba/", "urls": ["https://www.cd-cc.si/kultura/glasba"]}),
    ]],
    # Promotori (javni programi; robots.txt se provjerava prije čitanja) – prvo probe
    {"key": "hangtime", "venue": None, "probe": True, "probe_only": True, "allow_empty": True, "parser": "detail",
     "link_pattern": r"/hr/event/[\w-]{4,}", "limit": 40, "exclude": THEATRE, "urls": ["https://hangtimeagency.com/hr/"]},
    {"key": "laa", "venue": None, "probe": True, "probe_only": True, "allow_empty": True, "urls": ["https://www.laa.hr/"]},
    # Entrio: 10. 11. 2026. vraća 403 našem robotu (i za sitemap) – ne zaobilazimo, čekamo njihov odgovor.
    # InfoZagreb: kalendar se učitava tek u pregledniku (JavaScript), a sitemap.xml ne postoji – zasad nije izvor.
    # Maribor – prvo samo probe (struktura stranica), zatim aktivacija
    *[dict({"city": "maribor", "exclude": THEATRE, "dj_words": DJ, "probe": True, "probe_only": True, "allow_empty": True}, **x) for x in [
        {"key": "mb-narodnidom", "venue": None, "urls": ["https://nd-mb.si/narodni-dom-maribor/program-dogodkov-narodni-dom-maribor/"]},
        {"key": "mb-stuk", "venue": None, "urls": ["https://stuk.org/"]},
        {"key": "mb-sng", "venue": None, "urls": ["https://www.sng-mb.si/"]},
        {"key": "mb-mkc", "venue": None, "urls": ["https://www.mkc.si/"]},
    ]],
    {"key": "kinosiska", "city": "ljubljana", "venue": "lj-kinosiska", "probe": True,
     "parser": "rows", "row": "tr", "link": "/dogodek/", "row_require": "glasba", "exclude": ["dostava"],
     "urls": ["https://www.kinosiska.si/"]},
    {"key": "orto", "city": "ljubljana", "venue": "lj-orto", "probe": True, "no_time": True,  # vrijeme na popisu nije početak
     "urls": ["https://www.orto-bar.com/shop/?jsf=woocommerce-archive&tax=product_cat%3A194%2C226&sort=orderby%3Ameta_value%3Border%3AASC%3Bmeta_key%3Adatum-eventa"]},
]

# Ključne riječi za prepoznavanje žanra iz naslova (prvi pogodak pobjeđuje)
GENRE_WORDS = [
    ("djeca", ["za djecu", "dječj", "djecu", "minimini", "glazbena priča", "božićni sat", "vilenjak"]),
    ("jazz", ["jazz"]),
    ("blues", ["blues"]),
    ("hiphop", ["hip hop", "hip-hop", " rap ", " rapper", " trap ", "freestyle"]),
    ("opera", ["opera ", "opera:", "opere", "operet", "opernih", "balet"]),
    ("world", ["izvorišta", "sevdah", "flamenco", "drummers of japan"]),
    ("trad", ["klapa", "tambur", "folklor", "lado"]),
    ("klasika", ["filharmonij", "simfonij", "orkestar", "kvartet", "glasovir", "violin", "solisti", "orgulje",
                 "lisinski subotom", "da camera", "majstorski ciklus", "kanconijer", "rezidenti muza",
                 "guitarra viva", "glazbeni umjetnici zagrebu", "klavir", "mezzosopran"]),
    ("metal", ["metal"]),
    ("punk", ["punk", "hardcore"]),
    ("dj", ["party", "afterparty", "sound system", "hi-fi"]),
]
