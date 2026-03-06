# Mars Bleu Connecté 2026

Results scraper and static site generator for the **Défi Mars Bleu Connecté 2026** — a charity running/walking challenge for colorectal cancer awareness.

## How It Works

1. Scrapes participant data from [ZapSports](https://www.zapsports.com) (5 paginated result pages)
2. Parses HTML tables with regex (no external parser)
3. Generates a self-contained `index.html` with embedded CSS/JS

## Key Files

| File | Purpose |
|------|---------|
| `scrape.py` | Scraper + HTML generator (single script, stdlib only) |
| `Makefile` | Task runner (`make gen`, `make serve`) |
| `index.html` | Generated output (do not edit manually) |

## Data Flow

```
ZapSports (5 pages, 100 results each)
  → fetch_page(offset) via urllib
  → parse_page() extracts participant rows
  → scrape_all() aggregates all pages
  → generate_html() produces index.html
```

## Key Functions in `scrape.py`

- **`scrape_all()`** — fetches all 5 pages and returns a combined participant list
- **`fetch_page(offset)`** — HTTP GET a single ZapSports results page
- **`parse_page(page_html)`** — regex-parses an HTML table into participant dicts; handles detail rows (dossard, dénivelé, temps, place)
- **`generate_html(participants)`** — builds the full HTML page with Bulma styling
- **`km_float(p)`** — converts comma-decimal km string to float for sorting
- **`slugify(text)`** — URL-safe slug for team anchors
- **`clean(s)`** — strips HTML tags and normalizes whitespace
- **`cat_code(cat)` / `cat_fr(cat)`** — category code extraction and French label lookup

## Data Model

Each participant is a dict:

```python
{
    "nom": "Dupont Jean",      # name
    "km": "42,5",              # distance (comma decimal)
    "nb_seances": "12",        # number of sessions
    "sexe": "M",               # M or F
    "categorie": "SE-M",       # age category code
    "equipe": "Les Coureurs",  # team name
    "dossard": "123",          # bib number
    "denivele": "450",         # elevation in meters
    "temps": "04:30:00",       # time
    "place": "5",              # overall temporary rank
    "place_cat": "2",          # category temporary rank
}
```

## How to Run

```bash
make gen          # scrape + generate index.html
make serve        # serve on http://localhost:6302
python3 scrape.py --test   # scrape only, print sample data (no HTML generation)
```

## Generated Output

The `index.html` has 4 tabs:

- **Général** — all participants ranked by km
- **Par Équipe** — teams ranked by total km, expandable member lists
- **Par Sexe** — separate Femmes/Hommes sections
- **Par Catégorie** — grouped by age category (Minime → Master 9)

Features: stats cards (participants, km, teams), live search, column sorting, dark mode via `prefers-color-scheme`, responsive design.

## Dependencies

- **Python**: stdlib only (`urllib`, `re`, `html`, `json`, `datetime`) — no pip packages
- **Frontend**: [Bulma 1.0.4](https://bulma.io) + [Font Awesome 6.5](https://fontawesome.com) via CDN
