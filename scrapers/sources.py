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
    {"key": "petikupe", "venue": "petikupe", "parser": "detail", "dj_words": DJ,
     "link_pattern": r"petikupe\.com/(?!arhiva|kontakt|o-klubu|clubbing|wine-dine|konferencije|izlozbe|rezerviraj|category|tag|wp-)[a-z0-9-]{6,}/?$",
     "urls": ["https://petikupe.com/"]},
    {"key": "pogon", "venue": "pogon", "include": ["koncert", "concert"], "exclude": THEATRE, "allow_empty": True,
     "parser": "cards", "card": ".item-card", "title": ".event-title",
     "urls": ["https://www.pogon.hr/program/"]},
    # Ulaznice.hr: cijela Hrvatska na jednoj stranici – uzimamo samo Zagreb, prostor iz teksta
    {"key": "ulaznice", "venue": None, "require": "zagreb", "debug_always": True, "exclude": THEATRE + ["kazalište", "kino", "film"],
     "dj_words": DJ, "urls": ["https://www.ulaznice.hr/web/events"]},
    # Agregator: pokriva Arenu, Boogaloo, Vintage, Boćarski dom i manje klubove (JSON-LD MusicEvent)
    {"key": "songkick", "venue": None, "strip": [r"\s+@\s+.*$"], "outside": OUTSIDE,
     "urls": ["https://www.songkick.com/metro-areas/29037-croatia-zagreb",
              "https://www.songkick.com/metro-areas/29037-croatia-zagreb?page=2"]},
]

# Ključne riječi za prepoznavanje žanra iz naslova (prvi pogodak pobjeđuje)
GENRE_WORDS = [
    ("djeca", ["za djecu", "dječj", "djecu", "minimini", "glazbena priča", "božićni sat", "vilenjak"]),
    ("jazz", ["jazz"]),
    ("world", ["izvorišta", "sevdah", "flamenco", "drummers of japan"]),
    ("trad", ["klapa", "tambur", "folklor", "lado"]),
    ("klasika", ["filharmonij", "simfonij", "orkestar", "kvartet", "glasovir", "violin", "solisti", "orgulje",
                 "lisinski subotom", "da camera", "majstorski ciklus", "opera", "kanconijer", "rezidenti muza",
                 "guitarra viva", "glazbeni umjetnici zagrebu", "klavir", "mezzosopran"]),
    ("metal", ["metal"]),
    ("punk", ["punk", "hardcore"]),
    ("dj", ["party", "afterparty", "sound system", "hi-fi"]),
]
