#!/usr/bin/env python3
"""Scrape les résultats du Défi Mars Bleu Connecté 2026 depuis ZapSports
et génère un site HTML statique avec Bulma."""

import html as html_mod
import json
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://www.zapsports.com/ext/app_page_web/su-res-detail-503-{offset}-100.htm"
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


def clean(s):
    """Nettoie une cellule HTML : supprime les balises, normalise les espaces."""
    return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


def fetch_page(offset):
    """Récupère une page de résultats depuis ZapSports."""
    url = BASE_URL.format(offset=offset)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("latin-1")


def parse_page(page_html):
    """Parse une page HTML et retourne la liste des participants."""
    participants = []
    table_match = re.search(r"<table[^>]*>(.*?)</table>", page_html, re.DOTALL)
    if not table_match:
        return participants
    table = table_match.group(1)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)

    i = 1  # skip header row
    while i < len(rows):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", rows[i], re.DOTALL)
        if len(cells) >= 7:
            nom = clean(cells[3])
            if nom:
                p = {
                    "nb_seances": clean(cells[1]),
                    "km": clean(cells[2]),
                    "nom": nom,
                    "sexe": clean(cells[4]),
                    "categorie": clean(cells[5]),
                    "equipe": clean(cells[6]),
                    "dossard": "",
                    "denivele": "",
                    "temps": "",
                    "place": "",
                    "place_cat": "",
                }
                # Check next row for detail line
                if i + 1 < len(rows):
                    detail_cells = re.findall(
                        r"<td[^>]*>(.*?)</td>", rows[i + 1], re.DOTALL
                    )
                    if len(detail_cells) == 1:
                        detail = clean(detail_cells[0])
                        m = re.search(r"Dossard n° (\d+)", detail)
                        if m:
                            p["dossard"] = m.group(1)
                        m = re.search(r"Dénivelé : (\d+)m", detail)
                        if m:
                            p["denivele"] = m.group(1)
                        m = re.search(r"Temps : ([\d:]+)", detail)
                        if m:
                            p["temps"] = m.group(1)
                        m = re.search(r"Place temporaire : (\d+)", detail)
                        if m:
                            p["place"] = m.group(1)
                        m = re.search(r"Place cat\. temporaire : (\d+)", detail)
                        if m:
                            p["place_cat"] = m.group(1)
                        i += 1
                participants.append(p)
        i += 1
    return participants



def scrape_all():
    """Récupère tous les participants depuis les 5 pages."""
    all_participants = []
    for offset in OFFSETS:
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
            "<th>Sexe</th>",
            "<th>Catégorie</th>",
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
                f'<tr data-nom="{esc(p["nom"].lower())}" '
                f'data-km="{km_float(p)}" '
                f'data-seances="{esc(p["nb_seances"])}">'
            )
            lines.append(f'<td class="has-text-grey">{idx}</td>')
            lines.append(f'<td><strong>{esc(p["nom"])}</strong></td>')
            lines.append(f'<td class="has-text-weight-semibold">{esc(p["km"])}</td>')
            lines.append(f'<td>{esc(p["nb_seances"])}</td>')
            lines.append(f"<td>{sexe_tag}</td>")
            lines.append(f"<td>{cat_tag}</td>")
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
        total_km = sum(km_float(p) for p in members)
        teams.append({
            "equipe": equipe_original_name[key],
            "km": f"{total_km:.1f}".replace(".", ","),
            "nb_equipier": len(members),
        })
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
            f'</span>'
            f'<i class="fas fa-chevron-right equipe-chevron"></i>'
            f'</div>'
        )
        tab_equipe_parts.append(f'<div class="equipe-detail" style="display:none">')
        if members:
            tab_equipe_parts.append(render_table(members))
        else:
            tab_equipe_parts.append('<p class="has-text-grey-light ml-4">Aucun détail disponible</p>')
        tab_equipe_parts.append('</div></div>')
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
        color = "is-danger" if s_code == "F" else "is-info"
        tab_sexe_parts.append(
            f'<div class="section-box" id="sexe-{s_code.lower()}">'
            f'<div class="section-box-title">'
            f'<i class="fas {icon}"></i> {esc(s_label)} '
            f'<span class="tag tag-km">{s_km:.1f} km</span> '
            f'<span class="tag tag-count">{len(members)} participante{"s" if len(members) > 1 else ""}</span>'
            f"</div>"
        )
        tab_sexe_parts.append(render_table(members))
        tab_sexe_parts.append("</div>")
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
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@1.0.4/css/bulma.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔵</text></svg>">
<style>
/* ── CSS Custom Properties for theming ── */
:root {{
  --bg: #f0f4f8;
  --bg-card: #ffffff;
  --bg-card-hover: #f7f9fc;
  --text: #1a1a2e;
  --text-secondary: #5a6778;
  --text-muted: #8e99a9;
  --border: #e2e8f0;
  --border-light: #edf2f7;
  --accent: #2563eb;
  --accent-light: #dbeafe;
  --accent-dark: #1d4ed8;
  --hero-from: #0f172a;
  --hero-via: #1e3a5f;
  --hero-to: #1e40af;
  --stat-gradient-1: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  --stat-gradient-2: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  --stat-gradient-3: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
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
  --table-head-bg: #f8fafc;
  --table-row-hover: #f1f5f9;
  --table-border: #e2e8f0;
  --equipe-hover: #f8fafc;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 14px rgba(0,0,0,0.08);
  --shadow-lg: 0 10px 30px rgba(0,0,0,0.1);
  --radius: 12px;
  --radius-sm: 8px;
  --footer-bg: #f8fafc;
  --footer-text: #64748b;
  --input-bg: #ffffff;
  --input-border: #cbd5e1;
  --tab-bg: transparent;
  --tab-active-bg: var(--bg-card);
  --tab-active-border: var(--accent);
  --tab-text: var(--text-secondary);
  --tab-active-text: var(--accent);
}}

@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0f172a;
    --bg-card: #1e293b;
    --bg-card-hover: #263348;
    --text: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --border: #334155;
    --border-light: #1e293b;
    --accent: #60a5fa;
    --accent-light: #1e3a5f;
    --accent-dark: #93bbfc;
    --hero-from: #020617;
    --hero-via: #0f172a;
    --hero-to: #1e3a5f;
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
    --table-head-bg: #1a2536;
    --table-row-hover: #263348;
    --table-border: #334155;
    --equipe-hover: #263348;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 14px rgba(0,0,0,0.3);
    --shadow-lg: 0 10px 30px rgba(0,0,0,0.4);
    --footer-bg: #1e293b;
    --footer-text: #94a3b8;
    --input-bg: #1e293b;
    --input-border: #475569;
    --tab-active-bg: var(--bg-card);

    /* Bulma 1.0 variable overrides */
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
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  transition: background 0.3s, color 0.3s;
}}

/* ── Hero ── */
.hero-section {{
  background: linear-gradient(135deg, var(--hero-from) 0%, var(--hero-via) 40%, var(--hero-to) 100%);
  padding: 3rem 1.5rem 2.5rem;
  text-align: center;
  position: relative;
  overflow: hidden;
}}
.hero-section::before {{
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(ellipse at 30% 50%, rgba(96,165,250,0.15) 0%, transparent 60%),
              radial-gradient(ellipse at 70% 80%, rgba(139,92,246,0.1) 0%, transparent 50%);
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
  font-size: 2.2rem;
  font-weight: 800;
  color: #ffffff;
  margin: 0 0 0.5rem;
  letter-spacing: -0.5px;
  position: relative;
}}
.hero-subtitle {{
  color: rgba(255,255,255,0.7);
  font-size: 1rem;
  font-weight: 400;
  position: relative;
}}

/* ── Stats cards ── */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.25rem;
  margin: -2rem auto 2rem;
  max-width: 900px;
  padding: 0 1.5rem;
  position: relative;
  z-index: 2;
}}
.stat-card {{
  border-radius: var(--radius);
  padding: 1.5rem;
  text-align: center;
  color: #fff;
  box-shadow: var(--shadow-lg);
  transition: transform 0.2s ease;
}}
.stat-card:hover {{
  transform: translateY(-3px);
}}
.stat-card .stat-value {{
  font-size: 2.4rem;
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -1px;
}}
.stat-card .stat-label {{
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  opacity: 0.85;
  margin-top: 0.3rem;
}}
.stat-1 {{ background: var(--stat-gradient-1); }}
.stat-2 {{ background: var(--stat-gradient-2); }}
.stat-3 {{ background: var(--stat-gradient-3); }}

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
  border-radius: var(--radius-sm);
  color: var(--text);
  box-shadow: var(--shadow-sm);
  padding-left: 2.5rem;
  height: 2.75rem;
  transition: border-color 0.2s, box-shadow 0.2s;
}}
.search-wrapper .input::placeholder {{
  color: var(--text-muted);
}}
.search-wrapper .input:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-light);
}}
.search-wrapper .icon {{
  color: var(--text-muted);
}}

/* ── Tabs ── */
.tabs-container {{
  margin-bottom: 1.5rem;
}}
.tabs-container .tabs {{
  border-bottom: 2px solid var(--border);
}}
.tabs-container .tabs ul {{
  border-bottom: none;
}}
.tabs-container .tabs li a {{
  color: var(--tab-text);
  border: none;
  border-bottom: 3px solid transparent;
  padding: 0.75rem 1.25rem;
  margin-bottom: -2px;
  font-weight: 500;
  transition: color 0.2s, border-color 0.2s;
  background: transparent;
}}
.tabs-container .tabs li a:hover {{
  color: var(--accent);
  border-bottom-color: var(--accent-light);
  background: transparent;
}}
.tabs-container .tabs li.is-active a {{
  color: var(--tab-active-text);
  border-bottom-color: var(--tab-active-border);
  font-weight: 600;
  background: transparent;
}}

/* ── Tab content ── */
.tab-content {{
  display: none;
  animation: fadeIn 0.25s ease;
}}
.tab-content.is-active {{
  display: block;
}}
@keyframes fadeIn {{
  from {{ opacity: 0; transform: translateY(6px); }}
  to {{ opacity: 1; transform: translateY(0); }}
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
  background: var(--table-head-bg) !important;
  color: var(--text-secondary);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  font-weight: 600;
  border-bottom: 2px solid var(--border) !important;
  padding: 0.9rem 1rem;
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
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-light) !important;
  vertical-align: middle;
  font-size: 0.92rem;
}}
.results-table tbody tr {{
  transition: background 0.15s;
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
  font-size: 0.65rem;
  margin-left: 0.3rem;
  opacity: 0.5;
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
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}}
.section-box-title i {{
  font-size: 1.1rem;
  color: var(--accent);
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
  transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: none;
}}
.equipe-summary:hover {{
  background: var(--equipe-hover);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}}
.equipe-rank {{
  color: var(--text-muted);
  font-weight: 700;
  font-size: 1rem;
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
  border: 1px solid var(--accent);
  border-top: none;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
  padding: 0.75rem;
  background: var(--bg-card);
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
.site-footer a {{
  color: var(--accent);
  text-decoration: none;
}}
.site-footer a:hover {{
  text-decoration: underline;
}}

/* ── Responsive ── */
@media (max-width: 768px) {{
  .hero-title {{ font-size: 1.5rem; }}
  .hero-logo {{ width: 200px; }}
  .stat-card .stat-value {{ font-size: 1.8rem; }}
  .tabs-container .tabs li a {{ padding: 0.5rem 0.75rem; font-size: 0.85rem; }}
  .equipe-tags {{ display: none; }}
  .results-table {{ font-size: 0.85rem; }}
}}
</style>
</head>
<body>

<div class="hero-section">
  <img src="{logo_url}" alt="Mars Bleu" class="hero-logo">
  <h1 class="hero-title">Défi Mars Bleu Connecté 2026</h1>
  <p class="hero-subtitle">Résultats en direct &mdash; Mise à jour : {now}</p>
</div>

<div class="stats-grid">
  <div class="stat-card stat-1">
    <div class="stat-value">{total_participants}</div>
    <div class="stat-label">Participants</div>
  </div>
  <div class="stat-card stat-2">
    <div class="stat-value">{total_km:,.1f}</div>
    <div class="stat-label">Kilomètres</div>
  </div>
  <div class="stat-card stat-3">
    <div class="stat-value">{nb_equipes}</div>
    <div class="stat-label">Équipes</div>
  </div>
</div>

<div class="main-content">

  <div class="search-wrapper">
    <div class="control has-icons-left">
      <input class="input" type="text" id="search" placeholder="Rechercher un participant...">
      <span class="icon is-left"><i class="fas fa-search"></i></span>
    </div>
  </div>

  <div class="tabs-container">
    <div class="tabs is-medium" id="main-tabs">
      <ul>
        <li class="is-active" data-tab="general"><a href="#general"><i class="fas fa-list-ol mr-2"></i>Général</a></li>
        <li data-tab="equipe"><a href="#equipe"><i class="fas fa-users mr-2"></i>Par Équipe</a></li>
        <li data-tab="sexe"><a href="#sexe"><i class="fas fa-venus-mars mr-2"></i>Par Sexe</a></li>
        <li data-tab="categorie"><a href="#categorie"><i class="fas fa-layer-group mr-2"></i>Par Catégorie</a></li>
      </ul>
    </div>
  </div>

  <div id="tab-general" class="tab-content is-active">
    {tab_general}
  </div>
  <div id="tab-equipe" class="tab-content">
    {tab_equipe}
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
    <strong>Défi Mars Bleu Connecté 2026</strong> &mdash;
    Données issues de <a href="https://www.zapsports.com" target="_blank">ZapSports</a>.
    Mise à jour : {now}.
  </p>
  <p style="margin-top:0.5rem">
    <i class="fas fa-ribbon" style="color: var(--accent);"></i>
    Mars Bleu &mdash; Sensibilisation au cancer colorectal
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

// Toggle équipe expand/collapse
function toggleEquipe(summary) {{
  var block = summary.closest('.equipe-block');
  var detail = block.querySelector('.equipe-detail');
  block.classList.toggle('is-open');
  detail.style.display = block.classList.contains('is-open') ? 'block' : 'none';
}}

// Hash routing on load
function handleHash() {{
  var hash = location.hash.replace('#', '');
  if (!hash) return;
  var tabs = ['general', 'equipe', 'sexe', 'categorie'];
  if (tabs.indexOf(hash) !== -1) {{
    activateTab(hash);
    return;
  }}
  var el = document.getElementById(hash);
  if (el && el.classList.contains('equipe-block')) {{
    activateTab('equipe');
    el.classList.add('is-open');
    el.querySelector('.equipe-detail').style.display = 'block';
    setTimeout(function() {{ el.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }}, 100);
  }}
}}
handleHash();
window.addEventListener('hashchange', handleHash);

// Recherche
document.getElementById('search').addEventListener('input', function() {{
  var q = this.value.toLowerCase();
  document.querySelectorAll('tbody tr').forEach(function(row) {{
    var nom = row.getAttribute('data-nom') || '';
    row.style.display = nom.includes(q) ? '' : 'none';
  }});
}});

// Tri des colonnes
document.querySelectorAll('th[data-sort]').forEach(function(th) {{
  th.addEventListener('click', function() {{
    var table = th.closest('table');
    var tbody = table.querySelector('tbody');
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
                print(f"  {p['nom']} - {p['km']} km - {p['equipe']} ({p['sexe']}, {p['categorie']})")
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
