# Koncerti u Zagrebu

Svi koncerti i DJ večeri u Zagrebu na jednom mjestu, od Arene do Močvare.

## Kako radi

1. **Skupljači** (`scrapers/`) svako jutro posjete stranice s programom (Lisinski, Tvornica kulture, Močvara, Dva Osam, KSET, Attack, Ulaznice.hr, Core Event…) i spreme pronađene događaje u `data/scraped/<izvor>.json`.
2. **Build** (`build.py`) spoji te podatke s ručno unesenima (`data/manual.json`), makne duplikate i prošle datume, i izgradi stranicu u `site/`.
3. **GitHub Actions** (`.github/workflows/update.yml`) to pokreće automatski svaki dan i objavljuje stranicu na GitHub Pages.

Ako neki izvor padne ili mu se promijeni HTML, zadržavaju se njegovi zadnji podaci, a problem se vidi u `data/report.json`.

## Česti zadaci

- **Ručno dodati koncert** (npr. za Sax ili Klaonicu, koji objavljuju samo na društvenim mrežama): dodaj unos u `data/manual.json`.
- **Dodati novi prostor:** unos u `data/venues.json` (naziv, adresa, alternativni nazivi) i, ako ima stranicu s programom, unos u `scrapers/sources.py`.
- **Pokrenuti ručno:** kartica *Actions* → *Osvježi koncerte* → *Run workflow*.

## Lokalno

```bash
pip install -r requirements.txt
python -m scrapers.run      # skupi podatke (ili: python -m scrapers.run lisinski mocvara)
python build.py             # izgradi site/index.html
```

## Prvo postavljanje na GitHubu

Settings → Pages → *Build and deployment* → Source: **GitHub Actions**. Vlastita domena se dodaje u istom izborniku (*Custom domain*).
