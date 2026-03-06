#!/usr/bin/env python3
"""Scrape les résultats du Défi Mars Bleu Connecté 2026 depuis ZapSports
et génère un site HTML statique avec Bulma."""

import html as html_mod
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup

BASE_URL = (
    "https://www.zapsports.com/ext/app_page_web/su-res-detail-503-{offset}-100.htm"
)
OFFSETS = [0, 100, 200, 300, 400]

CATEGORIES_FR = {
    "MI": "Minime",
    "CA": "Cadet(te)",
    "ES": "Espoir",
    "SE": "Senior",
    "M0": "Master 0",
    "M1": "Master 1",
    "M2": "Master 2",
    "M3": "Master 3",
    "M4": "Master 4",
    "M5": "Master 5",
    "M6": "Master 6",
    "M7": "Master 7",
    "M8": "Master 8",
    "M9": "Master 9",
}

SEXE_FR = {"F": "Femmes", "M": "Hommes"}


def slugify(text):
    """Convertit un texte en slug URL-safe (ex: 'Les Ki Speed !' → 'les-ki-speed')."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def fetch_page(offset, retries=2):
    """Récupère une page de résultats depuis ZapSports (avec retry)."""
    url = BASE_URL.format(offset=offset)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("latin-1")
        except Exception as e:
            if attempt < retries:
                print(
                    f"    Erreur (tentative {attempt + 1}/{retries + 1}): {e}. Retry..."
                )
                time.sleep(5)
            else:
                raise


def parse_detail(text, p):
    """Extrait les champs de la ligne de détail (texte brut) dans le dict participant."""
    m = re.search(r"Dossard n[o°]\s*(\d+)", text)
    if m:
        p["dossard"] = m.group(1)
    m = re.search(r"D[ée]nivel[ée]\s*:\s*(\d+)\s*m", text)
    if m:
        p["denivele"] = m.group(1)
    m = re.search(r"Temps\s*:\s*([\d:]+)", text)
    if m:
        p["temps"] = m.group(1)
    m = re.search(r"Place cat\.\s*temporaire\s*:\s*(\d+)", text)
    if m:
        p["place_cat"] = m.group(1)
    m = re.search(r"Place temporaire\s*:\s*(\d+)", text)
    if m:
        p["place"] = m.group(1)


def parse_page(page_html):
    """Parse une page HTML avec BeautifulSoup et retourne la liste des participants."""
    participants = []
    soup = BeautifulSoup(page_html, "html.parser")
    table = soup.find("table")
    if not table:
        return participants

    rows = table.find_all("tr")
    if not rows:
        return participants

    # Build column index map from header row
    header_cells = rows[0].find_all(["th", "td"])
    col_map = {}
    for idx, th in enumerate(header_cells):
        text = th.get_text(" ", strip=True).lower()
        if "séance" in text or "seance" in text:
            col_map["nb_seances"] = idx
        elif "km" in text:
            col_map["km"] = idx
        elif "nom" in text:
            col_map["nom"] = idx
        elif "sexe" in text:
            col_map["sexe"] = idx
        elif "cat" in text:
            col_map["categorie"] = idx
        elif "entreprise" in text:
            col_map["entreprise"] = idx
        elif "equipe" in text or "équipe" in text:
            col_map["equipe"] = idx

    def get_col(cells, key, default=""):
        idx = col_map.get(key)
        if idx is None or idx >= len(cells):
            return default
        return cells[idx].get_text(" ", strip=True)

    i = 1  # skip header row
    while i < len(rows):
        tds = rows[i].find_all("td")
        if len(tds) > 2:
            nom = get_col(tds, "nom")
            if nom:
                p = {
                    "nb_seances": get_col(tds, "nb_seances"),
                    "km": get_col(tds, "km"),
                    "nom": nom,
                    "sexe": get_col(tds, "sexe"),
                    "categorie": get_col(tds, "categorie"),
                    "entreprise": get_col(tds, "entreprise"),
                    "equipe": get_col(tds, "equipe"),
                    "dossard": "",
                    "denivele": "",
                    "temps": "",
                    "place": "",
                    "place_cat": "",
                }
                # Check next row for detail line (single <td>)
                if i + 1 < len(rows):
                    next_tds = rows[i + 1].find_all("td")
                    if len(next_tds) == 1:
                        parse_detail(next_tds[0].get_text(" ", strip=True), p)
                        i += 1
                participants.append(p)
        i += 1
    return participants


def _detect_offsets(first_page_html):
    """Détecte dynamiquement tous les offsets depuis la pagination."""
    soup = BeautifulSoup(first_page_html, "html.parser")
    offsets = set(OFFSETS)  # fallback to hardcoded offsets
    for a in soup.find_all("a", href=True):
        m = re.search(r"su-res-detail-\d+-(\d+)-100\.htm", a["href"])
        if m:
            offsets.add(int(m.group(1)))
    return sorted(offsets)


def scrape_all():
    """Récupère tous les participants (détection dynamique des pages)."""
    all_participants = []
    print("  Récupération page offset=0 (détection pagination)...")
    first_html = fetch_page(0)
    offsets = _detect_offsets(first_html)
    print(f"  Pages détectées : offsets={offsets}")

    participants = parse_page(first_html)
    print(f"    → {len(participants)} participants")
    all_participants.extend(participants)

    for offset in offsets:
        if offset == 0:
            continue
        print(f"  Récupération page offset={offset}...")
        page_html = fetch_page(offset)
        participants = parse_page(page_html)
        print(f"    → {len(participants)} participants")
        all_participants.extend(participants)
    return all_participants


def cat_code(cat):
    """Extrait le code de catégorie sans le suffixe -F/-M."""
    return re.sub(r"-[FM]$", "", cat)


def cat_fr(cat):
    """Retourne le nom français d'une catégorie."""
    code = cat_code(cat)
    return CATEGORIES_FR.get(code, code)


def km_float(p):
    """Convertit le km en float pour le tri."""
    try:
        return float(p["km"].replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def generate_html(participants):
    """Génère le fichier index.html avec Bulma."""
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y à %H:%M UTC")
    participants_sorted = sorted(participants, key=km_float, reverse=True)
    total_km = sum(km_float(p) for p in participants)
    total_participants = len(participants)

    # Groupements
    sexes = {}
    for p in participants_sorted:
        s = p["sexe"] or "?"
        sexes.setdefault(s, []).append(p)

    categories = {}
    for p in participants_sorted:
        code = cat_code(p["categorie"])
        categories.setdefault(code, []).append(p)
    categories_sorted = sorted(
        categories.items(),
        key=lambda x: sum(km_float(p) for p in x[1]),
        reverse=True,
    )

    def esc(s):
        return html_mod.escape(str(s))

    def render_table(rows, table_id=""):
        """Génère un tableau HTML de participants."""
        tid = f' id="{table_id}"' if table_id else ""
        lines = [
            f'<table class="table is-hoverable is-fullwidth results-table"{tid}>',
            "<thead><tr>",
            '<th class="is-narrow">#</th>',
            '<th data-sort="nom">Nom <i class="fas fa-sort sort-icon"></i></th>',
            '<th data-sort="km">Km <i class="fas fa-sort sort-icon"></i></th>',
            '<th data-sort="seances">Séances <i class="fas fa-sort sort-icon"></i></th>',
            '<th data-sort="denivele">Dénivelé <i class="fas fa-sort sort-icon"></i></th>',
            "<th>Sexe</th>",
            "<th>Catégorie</th>",
            "<th>Entreprise</th>",
            "</tr></thead>",
            "<tbody>",
        ]
        for idx, p in enumerate(rows, 1):
            sexe_tag = (
                f'<span class="tag tag-sexe-m">{esc(p["sexe"])}</span>'
                if p["sexe"] == "M"
                else f'<span class="tag tag-sexe-f">{esc(p["sexe"])}</span>'
            )
            cat_tag = f'<span class="tag tag-cat">{esc(cat_fr(p["categorie"]))}</span>'
            lines.append(
                f'<tr class="participant-row" style="cursor:pointer" '
                f'data-nom="{esc(p["nom"].lower())}" '
                f'data-km="{km_float(p)}" '
                f'data-seances="{esc(p["nb_seances"])}" '
                f'data-denivele="{esc(p.get("denivele", "0"))}" '
                f'data-dossard="{esc(p.get("dossard", ""))}" '
                f'data-temps="{esc(p.get("temps", ""))}" '
                f'data-place="{esc(p.get("place", ""))}" '
                f'data-place-cat="{esc(p.get("place_cat", ""))}">'
            )
            denivele_val = p.get("denivele", "")
            lines.append(f'<td data-label="#">{idx}</td>')
            lines.append(f'<td data-label="Nom"><strong>{esc(p["nom"])}</strong></td>')
            lines.append(f'<td data-label="Km"><strong>{esc(p["km"])}</strong></td>')
            lines.append(f'<td data-label="Séances">{esc(p["nb_seances"])}</td>')
            lines.append(
                f'<td data-label="Dénivelé">{esc(denivele_val)}{" m" if denivele_val else ""}</td>'
            )
            lines.append(f'<td data-label="Sexe">{sexe_tag}</td>')
            lines.append(f'<td data-label="Catégorie">{cat_tag}</td>')
            lines.append(
                f'<td data-label="Entreprise">{esc(p.get("entreprise", ""))}</td>'
            )
            lines.append("</tr>")
        lines.append("</tbody></table>")
        return "\n".join(lines)

    # Onglet Général
    tab_general = render_table(participants_sorted, "table-general")

    # Onglet Par Équipe — build teams from participant data
    equipe_members = {}
    equipe_original_name = {}
    for p in participants_sorted:
        eq = p["equipe"]
        if eq:
            key = eq.lower()
            equipe_members.setdefault(key, []).append(p)
            if key not in equipe_original_name:
                equipe_original_name[key] = eq

    teams = []
    for key, members in equipe_members.items():
        team_km = sum(km_float(p) for p in members)
        teams.append(
            {
                "equipe": equipe_original_name[key],
                "km": f"{team_km:.1f}".replace(".", ","),
                "nb_equipier": len(members),
            }
        )
    teams.sort(key=lambda t: float(t["km"].replace(",", ".")), reverse=True)
    nb_equipes = len(teams)

    tab_equipe_parts = []
    for idx, t in enumerate(teams, 1):
        team_slug = slugify(t["equipe"])
        members = equipe_members.get(t["equipe"].lower(), [])
        tab_equipe_parts.append(
            f'<div class="equipe-block" id="equipe-{team_slug}">'
            f'<div class="equipe-summary" onclick="toggleEquipe(this)">'
            f'<span class="equipe-rank">{idx}</span>'
            f'<span class="equipe-name">{esc(t["equipe"])}</span>'
            f'<span class="equipe-tags">'
            f'<span class="tag tag-km">{esc(t["km"])} km</span>'
            f'<span class="tag tag-count">{t["nb_equipier"]} équipiers</span>'
            f"</span>"
            f'<i class="fas fa-chevron-right equipe-chevron"></i>'
            f"</div>"
        )
        tab_equipe_parts.append('<div class="equipe-detail">')
        if members:
            tab_equipe_parts.append(render_table(members))
        else:
            tab_equipe_parts.append(
                '<p class="has-text-grey-light ml-4">Aucun détail disponible</p>'
            )
        tab_equipe_parts.append("</div></div>")
    tab_equipe = "\n".join(tab_equipe_parts)

    # Onglet Par Sexe
    tab_sexe_parts = []
    for s_code in ["F", "M"]:
        members = sexes.get(s_code, [])
        if not members:
            continue
        s_label = SEXE_FR.get(s_code, s_code)
        s_km = sum(km_float(p) for p in members)
        icon = "fa-venus" if s_code == "F" else "fa-mars"
        tab_sexe_parts.append(
            f'<div class="section-box" id="sexe-{s_code.lower()}">'
            f'<div class="section-box-title" onclick="toggleSection(this)" style="cursor:pointer">'
            f'<i class="fas {icon}"></i> {esc(s_label)} '
            f'<span class="tag tag-km">{s_km:.1f} km</span> '
            f'<span class="tag tag-count">{len(members)} participante{"s" if len(members) > 1 else ""}</span>'
            f'<i class="fas fa-chevron-right equipe-chevron" style="margin-left:auto"></i>'
            f"</div>"
            f'<div class="section-detail">'
        )
        tab_sexe_parts.append(render_table(members))
        tab_sexe_parts.append("</div></div>")
    tab_sexe = "\n".join(tab_sexe_parts)

    # Onglet Par Catégorie
    tab_cat_parts = []
    for cat_c, members in categories_sorted:
        c_label = CATEGORIES_FR.get(cat_c, cat_c)
        c_km = sum(km_float(p) for p in members)
        tab_cat_parts.append(
            f'<div class="section-box" id="cat-{cat_c.lower()}">'
            f'<div class="section-box-title">'
            f'<i class="fas fa-layer-group"></i> {esc(c_label)} '
            f'<span class="tag tag-km">{c_km:.1f} km</span> '
            f'<span class="tag tag-count">{len(members)} participant{"s" if len(members) > 1 else ""}</span>'
            f"</div>"
        )
        tab_cat_parts.append(render_table(members))
        tab_cat_parts.append("</div>")
    tab_cat = "\n".join(tab_cat_parts)

    logo_url = "https://www.iledefrance.ars.sante.fr/system/files/styles/ars_detail_page_content/private/2023-03/vignette_MARSBLEU_0.jpg.webp?itok=1fl-F36g"

    html_content = f"""<!DOCTYPE html>
<html lang="fr" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Défi Mars Bleu Connecté 2026 - Résultats</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@1.0.4/css/bulma.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🌼</text></svg>">
<style>
:root {{
  --font-heading: 'Playfair Display', Georgia, 'Times New Roman', serif;
  --font-body: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --bg: #faf8f5;
  --bg-card: #ffffff;
  --bg-card-hover: #f7f5f0;
  --text: #0a1628;
  --text-secondary: #4a5568;
  --text-muted: #8e99a9;
  --border: #e5e1d8;
  --border-light: #f0ece4;
  --accent: #1a56db;
  --accent-light: rgba(26,86,219,0.08);
  --accent-dark: #1648b8;
  --gold: #d4a853;
  --hero-from: #0a1628;
  --hero-via: #112240;
  --hero-to: #1a56db;
  --tag-m-bg: #dbeafe;
  --tag-m-text: #1e40af;
  --tag-f-bg: #fce7f3;
  --tag-f-text: #be185d;
  --tag-cat-bg: #fef3c7;
  --tag-cat-text: #92400e;
  --tag-km-bg: #d1fae5;
  --tag-km-text: #065f46;
  --tag-count-bg: #e0e7ff;
  --tag-count-text: #3730a3;
  --table-row-hover: rgba(26,86,219,0.04);
  --equipe-hover: #f9f7f3;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
  --shadow-md: 0 4px 14px rgba(0,0,0,0.07);
  --shadow-lg: 0 10px 30px rgba(0,0,0,0.08);
  --radius: 12px;
  --radius-sm: 8px;
  --footer-bg: #faf8f5;
  --footer-text: #64748b;
  --input-bg: #ffffff;
  --input-border: #d5d0c8;
}}

@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0a1628;
    --bg-card: #111d32;
    --bg-card-hover: #162541;
    --text: #e8edf5;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --border: #1e3150;
    --border-light: #162541;
    --accent: #3b82f6;
    --accent-light: rgba(59,130,246,0.12);
    --accent-dark: #60a5fa;
    --gold: #e5b863;
    --hero-from: #020b1a;
    --hero-via: #0a1628;
    --hero-to: #1e3a6e;
    --tag-m-bg: #1e3a5f;
    --tag-m-text: #93c5fd;
    --tag-f-bg: #4a1942;
    --tag-f-text: #f9a8d4;
    --tag-cat-bg: #422006;
    --tag-cat-text: #fcd34d;
    --tag-km-bg: #064e3b;
    --tag-km-text: #6ee7b7;
    --tag-count-bg: #312e81;
    --tag-count-text: #a5b4fc;
    --table-row-hover: rgba(59,130,246,0.08);
    --equipe-hover: #162541;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 14px rgba(0,0,0,0.3);
    --shadow-lg: 0 10px 30px rgba(0,0,0,0.4);
    --footer-bg: #0a1628;
    --footer-text: #94a3b8;
    --input-bg: #111d32;
    --input-border: #1e3150;

    --bulma-text-strong: var(--text);
    --bulma-text: var(--text-secondary);
    --bulma-scheme-main: var(--bg);
    --bulma-scheme-main-bis: var(--bg-card);
    --bulma-scheme-main-ter: var(--bg-card-hover);
    --bulma-border: var(--border);
    --bulma-border-weak: var(--border-light);
    --bulma-table-color: var(--text);
    --bulma-table-cell-heading-color: var(--text-secondary);
    --bulma-table-head-cell-color: var(--text-secondary);
    --bulma-table-background-color: var(--bg-card);
    --bulma-table-cell-border-color: var(--border);
    --bulma-table-row-hover-background-color: var(--table-row-hover);
    --bulma-body-background-color: var(--bg);
    --bulma-body-color: var(--text);
    --bulma-strong-color: var(--text);
    --bulma-box-background-color: var(--bg-card);
    --bulma-footer-background-color: var(--footer-bg);
    --bulma-footer-color: var(--footer-text);
    --bulma-input-background-color: var(--input-bg);
    --bulma-input-border-color: var(--input-border);
    --bulma-input-color: var(--text);
  }}
}}

/* ── Global ── */
body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  transition: background 0.3s, color 0.3s;
}}
body::after {{
  content: '';
  position: fixed;
  top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: none;
  z-index: 9999;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");
}}

/* ── Hero ── */
.hero-section {{
  background: linear-gradient(135deg, var(--hero-from) 0%, var(--hero-via) 40%, var(--hero-to) 100%);
  background-size: 200% 200%;
  animation: heroGradient 8s ease infinite;
  padding: 3.5rem 1.5rem 3rem;
  text-align: center;
  position: relative;
  overflow: hidden;
}}
@keyframes heroGradient {{
  0%, 100% {{ background-position: 0% 50%; }}
  50% {{ background-position: 100% 50%; }}
}}
.hero-section::before {{
  content: '';
  position: absolute;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background: radial-gradient(ellipse at 30% 50%, rgba(96,165,250,0.12) 0%, transparent 60%),
              radial-gradient(ellipse at 70% 80%, rgba(212,168,83,0.08) 0%, transparent 50%);
  pointer-events: none;
}}
.hero-logo {{
  width: 280px;
  max-width: 70vw;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  margin-bottom: 1.5rem;
  position: relative;
}}
.hero-title {{
  font-family: var(--font-heading);
  font-size: 2.4rem;
  font-weight: 900;
  color: #ffffff;
  margin: 0 0 0.5rem;
  letter-spacing: -0.5px;
  position: relative;
}}
.hero-highlight {{
  position: relative;
  display: inline-block;
}}
.hero-highlight::after {{
  content: '';
  position: absolute;
  bottom: 2px;
  left: 0;
  width: 100%;
  height: 3px;
  background: var(--gold);
  border-radius: 2px;
}}
.hero-divider {{
  width: 60px;
  height: 3px;
  background: var(--gold);
  margin: 1rem auto 0.75rem;
  border-radius: 2px;
  position: relative;
}}
.hero-subtitle {{
  color: rgba(255,255,255,0.7);
  font-size: 1rem;
  font-weight: 400;
  position: relative;
  font-family: var(--font-body);
}}

/* ── Stats cards ── */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
  margin: -2rem auto 2rem;
  max-width: 900px;
  padding: 0 1.5rem;
  position: relative;
  z-index: 2;
}}
.stat-card {{
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 1.5rem;
  text-align: center;
  box-shadow: var(--shadow-md);
  border-top: 3px solid var(--accent);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  opacity: 0;
  animation: fadeInUp 0.6s ease forwards;
}}
.stat-card:nth-child(1) {{ animation-delay: 0s; }}
.stat-card:nth-child(2) {{ animation-delay: 0.1s; }}
.stat-card:nth-child(3) {{ animation-delay: 0.2s; }}
.stat-card:hover {{
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}}
.stat-card .stat-icon {{
  font-size: 1.2rem;
  color: var(--accent);
  margin-bottom: 0.5rem;
}}
.stat-card .stat-value {{
  font-family: var(--font-heading);
  font-size: 2.4rem;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -1px;
  color: var(--accent);
}}
.stat-card .stat-label {{
  font-family: var(--font-body);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--text-muted);
  margin-top: 0.4rem;
  font-weight: 500;
}}
@keyframes fadeInUp {{
  from {{ opacity: 0; transform: translateY(20px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

/* ── Main content ── */
.main-content {{
  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem;
}}

/* ── Search ── */
.search-wrapper {{
  max-width: 420px;
  margin-bottom: 1.5rem;
}}
.search-wrapper .input {{
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 50px;
  color: var(--text);
  box-shadow: var(--shadow-sm);
  padding-left: 2.75rem;
  height: 2.75rem;
  font-family: var(--font-body);
  transition: border-color 0.2s, box-shadow 0.2s;
}}
.search-wrapper .input::placeholder {{ color: var(--text-muted); }}
.search-wrapper .input:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-light);
}}
.search-wrapper .icon {{ color: var(--text-muted); }}

/* ── Tabs ── */
.tabs-container {{ margin-bottom: 1.5rem; }}
.tabs-container .tabs {{
  border-bottom: none;
}}
.tabs-container .tabs ul {{
  border-bottom: none;
  gap: 0.5rem;
}}
.tabs-container .tabs li a {{
  color: var(--text-secondary);
  border: 1.5px solid var(--border);
  border-radius: 50px;
  padding: 0.5rem 1.25rem;
  font-weight: 500;
  font-family: var(--font-body);
  font-size: 0.9rem;
  transition: all 0.2s ease;
  background: transparent;
  margin-bottom: 0;
}}
.tabs-container .tabs li a:hover {{
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-light);
}}
.tabs-container .tabs li.is-active a {{
  color: #ffffff;
  background: var(--accent);
  border-color: var(--accent);
  font-weight: 600;
}}

/* ── Tab content ── */
.tab-content {{
  display: none;
  animation: fadeInTab 0.3s ease;
}}
.tab-content.is-active {{ display: block; }}
@keyframes fadeInTab {{
  from {{ opacity: 0; }}
  to {{ opacity: 1; }}
}}

/* ── Tables ── */
.results-table {{
  background: var(--bg-card);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border);
}}
.results-table thead th {{
  background: transparent !important;
  color: var(--text-muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 500;
  font-family: var(--font-body);
  border-bottom: 2px solid var(--accent) !important;
  padding: 0.75rem 1rem;
  white-space: nowrap;
}}
.results-table,
.results-table thead,
.results-table tbody,
.results-table tr,
.results-table td,
.results-table th {{
  border-color: var(--border-light) !important;
}}
.results-table tbody td {{
  padding: 0.7rem 1rem;
  border-bottom: 1px solid var(--border-light) !important;
  vertical-align: middle;
  font-size: 0.9rem;
}}
.results-table tbody tr {{
  transition: background 0.15s;
}}
.results-table tbody tr:nth-child(even) {{
  background: rgba(0,0,0,0.015);
}}
@media (prefers-color-scheme: dark) {{
  .results-table tbody tr:nth-child(even) {{
    background: rgba(255,255,255,0.02);
  }}
}}
.results-table tbody tr:hover {{
  background: var(--table-row-hover) !important;
}}
.results-table tbody tr:last-child td {{
  border-bottom: none !important;
}}
th[data-sort] {{
  cursor: pointer;
  user-select: none;
}}
th[data-sort]:hover {{
  color: var(--accent) !important;
}}
.sort-icon {{
  font-size: 0.6rem;
  margin-left: 0.3rem;
  opacity: 0.4;
}}

/* ── Tags ── */
.tag-sexe-m {{
  background: var(--tag-m-bg) !important;
  color: var(--tag-m-text) !important;
  font-weight: 600;
  font-size: 0.75rem !important;
  border-radius: 6px;
}}
.tag-sexe-f {{
  background: var(--tag-f-bg) !important;
  color: var(--tag-f-text) !important;
  font-weight: 600;
  font-size: 0.75rem !important;
  border-radius: 6px;
}}
.tag-cat {{
  background: var(--tag-cat-bg) !important;
  color: var(--tag-cat-text) !important;
  font-weight: 500;
  font-size: 0.75rem !important;
  border-radius: 6px;
}}
.tag-km {{
  background: var(--tag-km-bg) !important;
  color: var(--tag-km-text) !important;
  font-weight: 700;
  font-size: 0.85rem !important;
  border-radius: 6px;
  padding: 0.4em 0.75em;
}}
.tag-count {{
  background: var(--tag-count-bg) !important;
  color: var(--tag-count-text) !important;
  font-weight: 600;
  font-size: 0.8rem !important;
  border-radius: 6px;
}}

/* ── Section boxes (sexe, categorie) ── */
.section-box {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: var(--shadow-sm);
}}
.section-box-title {{
  font-family: var(--font-body);
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  padding-left: 0.75rem;
  border-left: 3px solid var(--accent);
}}
.section-box-title i {{
  font-size: 1.1rem;
  color: var(--accent);
}}
.section-box-title i.equipe-chevron {{
  font-size: 0.85rem;
  color: var(--text-muted);
  transition: transform 0.25s ease, color 0.2s;
}}
.section-box.is-open .section-box-title i.equipe-chevron {{
  transform: rotate(90deg);
  color: var(--accent);
}}
.section-detail {{
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: max-height 0.4s ease, opacity 0.3s ease;
}}
.section-box.is-open .section-detail {{
  max-height: 50000px;
  opacity: 1;
}}

/* ── Équipe blocks ── */
.equipe-block {{
  margin-bottom: 0.5rem;
}}
.equipe-summary {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1rem 1.25rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, box-shadow 0.2s, transform 0.2s;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: none;
}}
.equipe-summary:hover {{
  background: var(--equipe-hover);
  border-color: var(--accent);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}}
.equipe-rank {{
  color: var(--text-muted);
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 1.1rem;
  min-width: 2rem;
  text-align: center;
}}
.equipe-name {{
  flex: 1;
  font-weight: 600;
  color: var(--text);
  font-size: 0.95rem;
}}
.equipe-tags {{
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}}
.equipe-chevron {{
  color: var(--text-muted);
  transition: transform 0.25s ease, color 0.2s;
  font-size: 0.85rem;
}}
.equipe-block.is-open .equipe-chevron {{
  transform: rotate(90deg);
  color: var(--accent);
}}
.equipe-block.is-open .equipe-summary {{
  border-color: var(--accent);
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
  background: var(--equipe-hover);
}}
.equipe-detail {{
  border: 1px solid var(--border);
  border-top: none;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
  padding: 0.75rem;
  background: var(--bg-card);
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: max-height 0.4s ease, opacity 0.3s ease, padding 0.3s ease;
  padding-top: 0;
  padding-bottom: 0;
}}
.equipe-block.is-open .equipe-detail {{
  max-height: 50000px;
  opacity: 1;
  padding: 0.75rem;
  border-color: var(--accent);
}}

/* ── Participant detail row ── */
.participant-detail-row td {{
  background: var(--bg-card-hover);
  padding: 0.75rem 1rem 0.75rem 2.5rem !important;
  border-bottom: 1px solid var(--border-light) !important;
}}
.participant-detail-row .detail-tags {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}}
.participant-detail-row .detail-tag {{
  background: var(--tag-count-bg);
  color: var(--tag-count-text);
  font-size: 0.8rem;
  font-weight: 500;
  border-radius: 6px;
  padding: 0.3em 0.7em;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}}
.participant-detail-row .detail-tag i {{
  font-size: 0.7rem;
  opacity: 0.7;
}}

/* ── Footer ── */
.site-footer {{
  background: var(--footer-bg);
  border-top: 1px solid var(--border);
  padding: 2rem 1.5rem;
  text-align: center;
  color: var(--footer-text);
  font-size: 0.88rem;
  margin-top: 3rem;
}}
.site-footer .footer-brand {{
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 1rem;
  color: var(--text);
}}
.site-footer a {{
  color: var(--accent);
  text-decoration: none;
}}
.site-footer a:hover {{ text-decoration: underline; }}
.footer-vibed {{
  margin-top: 0.75rem;
  font-size: 0.8rem;
}}
.footer-vibed .rainbow {{
  background: linear-gradient(90deg, #ff0000, #ff7700, #ffdd00, #00ff00, #0000ff, #8b00ff, #ff0000);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: rainbowFlow 3s linear infinite;
  font-weight: 700;
}}
@keyframes rainbowFlow {{
  0% {{ background-position: 0% 50%; }}
  100% {{ background-position: 200% 50%; }}
}}

/* ── Mobile responsive ── */
@media (max-width: 768px) {{
  /* Hero */
  .hero-section {{ padding: 2rem 1rem 2rem; }}
  .hero-title {{ font-size: 1.6rem; }}
  .hero-logo {{ width: 180px; }}

  /* Stats: single column, horizontal layout */
  .stats-grid {{
    grid-template-columns: 1fr;
    gap: 0.75rem;
    max-width: 400px;
  }}
  .stat-card {{
    display: flex;
    align-items: center;
    text-align: left;
    padding: 1rem 1.25rem;
    gap: 1rem;
  }}
  .stat-card .stat-icon {{
    font-size: 1.4rem;
    margin-bottom: 0;
  }}
  .stat-card .stat-value {{
    font-size: 1.6rem;
  }}
  .stat-card .stat-label {{
    margin-top: 0;
  }}

  /* Tabs: horizontal scroll pills */
  .tabs-container .tabs ul {{
    flex-wrap: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scroll-snap-type: x mandatory;
    padding-bottom: 0.25rem;
  }}
  .tabs-container .tabs li {{
    flex-shrink: 0;
    scroll-snap-align: start;
  }}
  .tabs-container .tabs li a {{
    padding: 0.4rem 0.9rem;
    font-size: 0.8rem;
    white-space: nowrap;
  }}

  /* Search: full width */
  .search-wrapper {{
    max-width: 100%;
  }}

  /* Tables: card-style rows */
  .results-table thead {{ display: none; }}
  .results-table tbody tr.participant-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.2rem;
    padding: 0.75rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0.5rem;
    border-radius: var(--radius-sm);
  }}
  .results-table tbody td {{
    border: none !important;
    padding: 0.2rem 0 !important;
    font-size: 0.85rem;
  }}
  .results-table tbody td::before {{
    content: attr(data-label);
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    display: block;
    font-weight: 500;
  }}
  /* Name spans full width */
  .results-table tbody td:nth-child(2) {{
    grid-column: 1 / -1;
  }}
  .results-table tbody tr.participant-detail-row {{
    display: block;
    padding: 0.5rem 0.75rem;
  }}
  .results-table tbody tr.participant-detail-row td {{
    padding: 0.5rem !important;
  }}
  .results-table tbody tr.participant-detail-row td::before {{
    display: none;
  }}

  /* Team blocks: keep tags visible */
  .equipe-tags {{
    display: flex;
    gap: 0.35rem;
  }}
  .equipe-tags .tag {{
    font-size: 0.7rem !important;
    padding: 0.2em 0.5em;
  }}
  .equipe-summary {{
    padding: 0.75rem 1rem;
    gap: 0.5rem;
    flex-wrap: wrap;
  }}
  .equipe-name {{
    min-width: 0;
    flex-basis: calc(100% - 3rem);
  }}
  .equipe-tags {{
    flex-basis: 100%;
    padding-left: 2rem;
  }}

  /* Section boxes */
  .section-box {{
    padding: 1rem;
  }}
}}

/* Hero Logo Link */
.hero-section a {{
  display: inline-block;
  transition: transform 0.3s ease;
}}

.hero-section a:hover img {{
  transform: scale(1.05);
}}

/* Theme Switcher */
.theme-switcher {{
  position: fixed;
  top: 1.5rem;
  right: 1.5rem;
  z-index: 1000;
}}

.theme-btn {{
  background: linear-gradient(135deg, var(--accent), var(--accent-dark));
  border: none;
  color: white;
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  cursor: pointer;
  font-size: 1.2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-md);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}}

.theme-btn:hover {{
  transform: scale(1.1) rotate(20deg);
  box-shadow: var(--shadow-lg);
}}

.theme-btn:active {{
  transform: scale(0.95);
}}

.theme-btn i {{
  transition: transform 0.3s ease;
}}

.theme-btn i.fa-sun {{
  color: #fbbf24;
}}

.theme-btn i.fa-moon {{
  color: #60a5fa;
}}

/* Improved Footer */
.site-footer {{
  background: var(--footer-bg);
  color: var(--footer-text);
  padding: 3rem 2rem 2rem;
  margin-top: 4rem;
  border-top: 2px solid var(--border);
  font-size: 0.9rem;
}}

.site-footer p {{
  margin: 0.75rem 0;
  line-height: 1.6;
}}

.site-footer a {{
  color: var(--accent);
  text-decoration: none;
  transition: all 0.2s ease;
}}

.site-footer a:hover {{
  text-decoration: underline;
  opacity: 0.8;
}}

.footer-brand {{
  font-family: var(--font-heading);
  font-weight: 700;
  color: var(--accent);
  font-size: 1.1rem;
}}

.footer-vibed {{
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: 1.5rem !important;
}}

.rainbow {{
  background: linear-gradient(90deg, #ff6b6b, #ffa500, #ffff00, #00ff00, #0000ff, #4b0082, #9400d3);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-style: italic;
  font-weight: 600;
}}

@media (max-width: 768px) {{
  .theme-switcher {{
    top: 1rem;
    right: 1rem;
  }}

  .theme-btn {{
    width: 2.5rem;
    height: 2.5rem;
    font-size: 1rem;
  }}
}}
</style>
</head>
<body>

<div class="theme-switcher">
  <button id="theme-toggle" class="theme-btn" title="Toggle dark mode">
    <i class="fas fa-moon"></i>
  </button>
</div>

<div class="hero-section">
  <a href="https://www.marsbleuconnecte.fr/#top" target="_blank" title="Aller au site Mars Bleu Connecté">
    <img src="{logo_url}" alt="Mars Bleu" class="hero-logo">
  </a>
  <h1 class="hero-title">Défi <span class="hero-highlight">Mars Bleu</span> Connecté 2026</h1>
  <div class="hero-divider"></div>
  <p class="hero-subtitle">Résultats en direct &mdash; Mise à jour : {now}</p>
</div>

<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-icon"><i class="fas fa-users"></i></div>
    <div>
      <div class="stat-value">{total_participants}</div>
      <div class="stat-label">Participants</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon"><i class="fas fa-road"></i></div>
    <div>
      <div class="stat-value">{total_km:,.1f}</div>
      <div class="stat-label">Kilomètres</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon"><i class="fas fa-people-group"></i></div>
    <div>
      <div class="stat-value">{nb_equipes}</div>
      <div class="stat-label">Équipes</div>
    </div>
  </div>
</div>

<div class="main-content">

  <div class="search-wrapper">
    <div class="control has-icons-left">
      <input class="input" type="text" id="search" placeholder="Rechercher un participant ou une équipe...">
      <span class="icon is-left"><i class="fas fa-search"></i></span>
    </div>
  </div>

  <div class="tabs-container">
    <div class="tabs is-medium" id="main-tabs">
      <ul>
        <li class="is-active" data-tab="equipe"><a href="#equipe"><i class="fas fa-users mr-2"></i>Par Équipe</a></li>
        <li data-tab="general"><a href="#general"><i class="fas fa-list-ol mr-2"></i>Général</a></li>
        <li data-tab="sexe"><a href="#sexe"><i class="fas fa-venus-mars mr-2"></i>Par Sexe</a></li>
        <li data-tab="categorie"><a href="#categorie"><i class="fas fa-layer-group mr-2"></i>Par Catégorie</a></li>
      </ul>
    </div>
  </div>

  <div id="tab-equipe" class="tab-content is-active">
    {tab_equipe}
  </div>
  <div id="tab-general" class="tab-content">
    {tab_general}
  </div>
  <div id="tab-sexe" class="tab-content">
    {tab_sexe}
  </div>
  <div id="tab-categorie" class="tab-content">
    {tab_cat}
  </div>

</div>

<footer class="site-footer">
  <p>
    <span class="footer-brand">Défi Mars Bleu Connecté 2026</span> &mdash;
    Données issues de <a href="https://www.zapsports.com" target="_blank">ZapSports</a>.
    Mise à jour : {now}.
  </p>
  <p style="margin-top:0.5rem">
    <i class="fas fa-ribbon" style="color: var(--gold);"></i>
    <span style="font-family: var(--font-heading); font-weight: 700;">Mars Bleu</span> &mdash; Sensibilisation au cancer colorectal
  </p>
  <p class="footer-vibed">
    <span class="rainbow">Vibed with love</span> by <a href="https://www.instagram.com/samchmou/" target="_blank">SamChmou</a> - <a href="https://www.instagram.com/nicerunners06/" target="_blank">Nice Runners</a>
  </p>
</footer>

<script>
// Activation d'un onglet
function activateTab(name) {{
  document.querySelectorAll('#main-tabs li').forEach(function(t) {{ t.classList.remove('is-active'); }});
  document.querySelectorAll('.tab-content').forEach(function(c) {{ c.classList.remove('is-active'); }});
  var tab = document.querySelector('#main-tabs li[data-tab="' + name + '"]');
  if (tab) {{
    tab.classList.add('is-active');
    document.getElementById('tab-' + name).classList.add('is-active');
  }}
}}

// Onglets avec hash
document.querySelectorAll('#main-tabs li').forEach(function(tab) {{
  tab.addEventListener('click', function(e) {{
    e.preventDefault();
    var name = tab.dataset.tab;
    activateTab(name);
    history.replaceState(null, '', '#' + name);
  }});
}});

// Toggle équipe expand/collapse with max-height animation
function toggleEquipe(summary) {{
  var block = summary.closest('.equipe-block');
  block.classList.toggle('is-open');
}}

// Toggle section-box (sexe) expand/collapse with max-height animation
function toggleSection(title) {{
  var box = title.closest('.section-box');
  box.classList.toggle('is-open');
}}

// Hash routing on load
function handleHash() {{
  var hash = location.hash.replace('#', '');
  if (!hash) return;
  var tabs = ['equipe', 'general', 'sexe', 'categorie'];
  if (tabs.indexOf(hash) !== -1) {{
    activateTab(hash);
    return;
  }}
  var el = document.getElementById(hash);
  if (el && el.classList.contains('equipe-block')) {{
    activateTab('equipe');
    el.classList.add('is-open');
    setTimeout(function() {{ el.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }}, 100);
  }}
}}
handleHash();
window.addEventListener('hashchange', handleHash);

// Recherche (onglet actif uniquement)
function applySearch(q) {{
  var activeTab = document.querySelector('.tab-content.is-active');
  if (!activeTab) return;
  var equipeBlocks = activeTab.querySelectorAll('.equipe-block');
  if (equipeBlocks.length > 0) {{
    equipeBlocks.forEach(function(block) {{
      var teamName = (block.querySelector('.equipe-name')?.textContent || '').toLowerCase();
      var members = block.querySelectorAll('tbody tr[data-nom]');
      var match = teamName.includes(q);
      if (!match) {{
        members.forEach(function(row) {{
          if ((row.getAttribute('data-nom') || '').includes(q)) match = true;
        }});
      }}
      block.style.display = match ? '' : 'none';
    }});
    // Auto-expand if exactly one team matches
    var visibleBlocks = Array.from(equipeBlocks).filter(function(b) {{ return b.style.display !== 'none'; }});
    if (visibleBlocks.length === 1) {{
      visibleBlocks[0].classList.add('is-open');
    }} else {{
      equipeBlocks.forEach(function(block) {{
        block.classList.remove('is-open');
      }});
    }}
  }} else {{
    activeTab.querySelectorAll('tbody tr').forEach(function(row) {{
      if (row.classList.contains('participant-detail-row')) {{ row.remove(); return; }}
      var nom = row.getAttribute('data-nom') || '';
      row.style.display = nom.includes(q) ? '' : 'none';
    }});
  }}
}}
document.getElementById('search').addEventListener('input', function() {{
  applySearch(this.value.toLowerCase());
}});
// Reset search display when switching tabs
document.querySelectorAll('#main-tabs li').forEach(function(tab) {{
  tab.addEventListener('click', function() {{
    var q = document.getElementById('search').value.toLowerCase();
    setTimeout(function() {{ applySearch(q); }}, 0);
  }});
}});

// Toggle participant detail row
document.addEventListener('click', function(e) {{
  var row = e.target.closest('tr.participant-row');
  if (!row) return;
  var next = row.nextElementSibling;
  if (next && next.classList.contains('participant-detail-row')) {{
    next.remove();
    return;
  }}
  var fields = [
    {{key: 'dossard', label: 'Dossard', icon: 'fa-hashtag'}},
    {{key: 'denivele', label: 'Dénivelé', icon: 'fa-mountain', suffix: ' m'}},
    {{key: 'temps', label: 'Temps', icon: 'fa-clock'}},
    {{key: 'place', label: 'Place temporaire', icon: 'fa-ranking-star'}},
    {{key: 'place-cat', label: 'Place catégorie', icon: 'fa-medal'}}
  ];
  var tags = '';
  fields.forEach(function(f) {{
    var val = row.getAttribute('data-' + f.key) || '';
    if (val) {{
      tags += '<span class="detail-tag"><i class="fas ' + f.icon + '"></i> ' + f.label + ' : ' + val + (f.suffix || '') + '</span>';
    }}
  }});
  if (!tags) return;
  var cols = row.querySelectorAll('td').length;
  var detailRow = document.createElement('tr');
  detailRow.className = 'participant-detail-row';
  detailRow.innerHTML = '<td colspan="' + cols + '"><div class="detail-tags">' + tags + '</div></td>';
  row.after(detailRow);
}});

// Tri des colonnes
document.querySelectorAll('th[data-sort]').forEach(function(th) {{
  th.addEventListener('click', function() {{
    var table = th.closest('table');
    var tbody = table.querySelector('tbody');
    tbody.querySelectorAll('tr.participant-detail-row').forEach(function(r) {{ r.remove(); }});
    var rows = Array.from(tbody.querySelectorAll('tr'));
    var key = th.dataset.sort;
    var asc = th.classList.toggle('asc');
    rows.sort(function(a, b) {{
      var va, vb;
      if (key === 'km') {{
        va = parseFloat(a.dataset.km) || 0;
        vb = parseFloat(b.dataset.km) || 0;
      }} else if (key === 'seances') {{
        va = parseInt(a.dataset.seances) || 0;
        vb = parseInt(b.dataset.seances) || 0;
      }} else if (key === 'denivele') {{
        va = parseInt(a.dataset.denivele) || 0;
        vb = parseInt(b.dataset.denivele) || 0;
      }} else {{
        va = a.dataset.nom || '';
        vb = b.dataset.nom || '';
      }}
      if (va < vb) return asc ? -1 : 1;
      if (va > vb) return asc ? 1 : -1;
      return 0;
    }});
    rows.forEach(function(row, idx) {{
      row.querySelector('td').textContent = idx + 1;
      tbody.appendChild(row);
    }});
  }});
}});

// Theme Toggle
document.addEventListener('DOMContentLoaded', function() {{
  const themeToggle = document.getElementById('theme-toggle');
  const html = document.documentElement;

  // Load saved theme preference or detect system preference
  const savedTheme = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');

  html.setAttribute('data-theme', initialTheme);
  updateThemeIcon(initialTheme);

  // Toggle theme on button click
  themeToggle.addEventListener('click', function() {{
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
  }});

  function updateThemeIcon(theme) {{
    const icon = themeToggle.querySelector('i');
    icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
  }}
}});
</script>

</body>
</html>"""
    return html_content


def main():
    if "--test" in sys.argv:
        print("Mode test : scraping des données...")
        participants = scrape_all()
        print(f"\nTotal : {len(participants)} participants")
        if participants:
            print("\nExemples :")
            for p in participants[:5]:
                print(
                    f"  {p['nom']} - {p['km']} km - {p['equipe']} ({p['sexe']}, {p['categorie']})"
                )
        return

    print("Scraping des résultats Mars Bleu...")
    participants = scrape_all()
    print(f"\nTotal : {len(participants)} participants")

    print("Génération du HTML...")
    html_content = generate_html(participants)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("index.html généré avec succès.")


if __name__ == "__main__":
    main()
