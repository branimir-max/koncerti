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
OUTSIDE = ["maribor", "čakovec", "cakovec", "zabok", "regenerator", "karlovac", "mala scena", "varaždin",
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
     "urls": ["https://www.tvornicakulture.com/"]},
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
    # Boogaloo: stranica ima zaštitu od botova, pa ga pokrivamo preko Songkicka.
    {"key": "vintage", "venue": "vintage", "dj_words": DJ,
     "urls": ["https://vintageindustrial-bar.com/"]},
    # Peti Kupe: na stranicama događaja nema pouzdanog datuma – pokriva ga Ulaznice.hr/Songkick.
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
    # Agregator: pokriva Arenu, Boogaloo, Vintage, Boćarski dom i manje klubove (JSON-LD MusicEvent)
    {"key": "songkick", "venue": None, "strip": [r"\s+@\s+.*$"], "outside": OUTSIDE, "locality": True,
     "urls": ["https://www.songkick.com/metro-areas/29037-croatia-zagreb",
              "https://www.songkick.com/metro-areas/29037-croatia-zagreb?page=2"]},

    # ---------- Drugi gradovi ----------
    # Split i Zabok stižu preko Ulaznice.hr i Core Eventa (gore). Songkick daje osnovu za
    # svaki grad ("locality": samo događaji kojima je mjesto baš taj grad, ne okolica),
    # a službeni programi klubova dodaju se jedan po jedan.
    *[{"key": f"songkick-{city}", "city": city, "venue": None, "strip": [r"\s+@\s+.*$"], "locality": True,
       "allow_empty": True, "urls": [f"https://www.songkick.com/metro-areas/{metro}"] +
       [f"https://www.songkick.com/metro-areas/{metro}?page={n}" for n in range(2, pages + 1)]}
      for city, metro, pages in [("ljubljana", "32259-slovenia-ljubljana", 3), ("split", "29035-croatia-split", 1), ("rijeka", "29032-croatia-rijeka", 1),
                                 ("budimpesta", "29047-hungary-budapest", 4), ("bec", "26771-austria-vienna", 5)]],
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
    {"key": "kinosiska", "city": "ljubljana", "venue": "lj-kinosiska", "debug_always": True,
     "urls": ["https://www.kinosiska.si/"]},
    {"key": "orto", "city": "ljubljana", "venue": "lj-orto", "debug_always": True,
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
