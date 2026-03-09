#!/usr/bin/env python3
"""Scrape les résultats du Défi Mars Bleu Connecté 2026 depuis ZapSports
et génère un site HTML statique avec Bulma."""

import html as html_mod
import os
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

LOGO_URL = "https://www.iledefrance.ars.sante.fr/system/files/styles/ars_detail_page_content/private/2023-03/vignette_MARSBLEU_0.jpg.webp?itok=1fl-F36g"
SUBSCRIBE_VIDEO_URL = "video-comment-faire.mp4"
BASE_URL = (
    "https://www.zapsports.com/ext/app_page_web/su-res-detail-503-{offset}-100.htm"
)
OFFSETS = [0, 100, 200, 300, 400]
OUTPUT_DIR = "html"

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


def get_paris_time():
    """Retourne l'heure actuelle en heure de Paris (CET/CEST)."""
    utc_now = datetime.now(timezone.utc)
    # Déterminer si on est en heure d'été (CEST) ou d'hiver (CET)
    # Transition : dernier dimanche de mars à 2h UTC et dernier dimanche d'octobre à 3h UTC
    year = utc_now.year

    # Dernier dimanche de mars (transition vers CEST)
    march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
    while march_last.weekday() != 6:  # 6 = dimanche
        march_last -= timedelta(days=1)

    # Dernier dimanche d'octobre (transition vers CET)
    october_last = datetime(year, 10, 31, tzinfo=timezone.utc)
    while october_last.weekday() != 6:  # 6 = dimanche
        october_last -= timedelta(days=1)

    # CEST : UTC+2, CET : UTC+1
    if march_last <= utc_now < october_last:
        offset = timedelta(hours=2)
    else:
        offset = timedelta(hours=1)

    paris_tz = timezone(offset)
    paris_now = utc_now.astimezone(paris_tz)
    return paris_now.strftime("%d/%m/%Y à %H:%M")


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


# 20 km par niveau jusqu’à 1000 (50 niveaux)
BADGE_THRESHOLDS = list(range(20, 1000 + 20, 20))

BADGE_REWARDS = [
    # index 0 : < 20 km
    ("Roi du Canapé 🛋️", "Tu as lâché la télécommande. Héroïque."),
    # 20 km
    (
        "Trotteur Prudent 🐢",
        "Le premier pas, c’est le plus dur. Le deuxième aussi. Le troisième pareil. Mais bon.",
    ),
    # 40 km
    (
        "Joggeur du Dimanche 🚶",
        "Tu cours. Officiellement. Ta famille ne te croit pas encore.",
    ),
    # 60 km
    ("Mollets en Devenir 🦵", "Tes chaussures ont commencé à te respecter timidement."),
    # 80 km
    (
        "Candidat Sérieux 📋",
        "Tu as dépensé plus en running qu’en pizza. La rupture est en cours.",
    ),
    # 100 km
    (
        "Boule d'Acier 🍑",
        "Tu peux faire du vélo pendant plus de 200km sans avoir de douleur.",
    ),
    # 120 km
    (
        "Killian Jornet en Carton 🏃💨",
        "Cours Killian, cours. Mais à ton rythme, hein, pas la peine de se blesser.",
    ),
    # 140 km
    (
        "Brûleur de Semelles 🔥",
        "Le vent commence à te regarder bizarrement. Il sent la concurrence.",
    ),
    # 160 km
    (
        "Cyborg des Faubourgs 🦾",
        "Mi-humain, mi-moteur diesel. Le mécanicien est impressionné.",
    ),
    # 180 km
    ("Rocket Man 🚀", "La NASA a mis ton dossier dans la pile ‘à surveiller’."),
    # 200 km
    (
        "Explorateur du Macadam 🌍",
        "200 km. Tu aurais pu aller jusqu’en Belgique. Tu aurais pu.",
    ),
    # 220 km
    (
        "Alien du Sport 👽",
        "Tes collègues se demandent si tu dors vraiment ou si tu cours pendant ce temps-là.",
    ),
    # 240 km
    ("Marathonien Autoproclamé 🏛️", "L’Olympe a reçu ton CV. Ils étudient le dossier."),
    # 260 km
    (
        "Conquérant des Ronds-Points 🛤️",
        "Tu connais chaque craquelure du bitume par son prénom.",
    ),
    # 280 km
    (
        "Avaleur de Bornes 🎯",
        "Les panneaux kilométriques font des cauchemars avec toi dedans.",
    ),
    # 300 km
    (
        "Phénomène Météo 🌪️",
        "Météo France t’a officiellement classé ‘perturbation localisée’.",
    ),
    # 320 km
    (
        "Chameau Turbo 🏜️",
        "Même les chameaux t’ont demandé ton secret. Tu as refusé de répondre.",
    ),
    # 340 km
    (
        "Coureur Quantique ⚛️",
        "Tu existes sur plusieurs parcours simultanément. Schrödinger était moins actif.",
    ),
    # 360 km
    (
        "Gladiateur du Goudron ⚔️",
        "Ave César ! Les km te saluent. César aussi, à contrecœur.",
    ),
    # 380 km
    (
        "Comète Humaine ☄️",
        "Tu laisses une traînée de sueur cosmique. Spectaculaire et légèrement repoussant.",
    ),
    # 400 km
    (
        "GPS Dépassé 🦾",
        "Le GPS a rendu les armes. Tu vas dans des endroits qu’il ne connaît pas.",
    ),
    # 420 km
    (
        "Prophète de la Foulée 📜",
        "Tes kilomètres sont cités dans des groupes WhatsApp que tu ne soupçonnes pas.",
    ),
    # 440 km
    (
        "Sphinx du Running 🦁",
        "Personne ne comprend comment tu fais. Toi non plus, mais tu continues.",
    ),
    # 460 km
    (
        "Nomade Cosmique 🌌",
        "Tu cours entre les étoiles. Ou presque. C’est surtout le périphérique, mais dans ta tête…",
    ),
    # 480 km
    (
        "Légende en Fabrication ⚡",
        "Dans 1000 ans, les historiens auront une section entière sur toi.",
    ),
    # 500 km
    (
        "Forgeron de l’Endurance 🔨",
        "500 km forgés à la sueur. Ton enclume, c’est le bitume.",
    ),
    # 520 km
    (
        "Titan des Kilomètres 🗿",
        "Les montagnes s’écartent. Les collines font une haie d’honneur.",
    ),
    # 540 km
    (
        "Dompteur d’Horizons 🌅",
        "L’horizon recule chaque fois que tu approches. Il a peur.",
    ),
    # 560 km
    (
        "Phénix de l’Asphalte 🔥🦅",
        "Tu renais à chaque kilomètre. Et tu es encore plus agaçant qu’avant.",
    ),
    # 580 km
    (
        "Demi-Dieu en Approche 👑",
        "Zeus a commandé tes chaussures pour voir ce que ça fait.",
    ),
    # === TIER LÉGENDAIRE (600 km+) ===
    # 600 km
    (
        "⭐ LÉGENDAIRE ⭐ Seigneur des Foulées 🐉",
        "Les médecins étudient tes mollets en cours magistral. La salle est comble.",
    ),
    # 620 km
    (
        "⭐ LÉGENDAIRE ⭐ Arpenteur des Galaxies 🪐",
        "Pluton t’a envoyé un message : ‘Respect. Sincèrement.’",
    ),
    # 640 km
    (
        "⭐ LÉGENDAIRE ⭐ Requin du Bitume 🦈",
        "La route disparaît sous tes pieds avant que tu arrives dessus.",
    ),
    # 660 km
    (
        "⭐ LÉGENDAIRE ⭐ Architecte de l’Impossible 🏗️",
        "Tu construis l’impossible un km à la fois. Le chantier est rentable.",
    ),
    # 680 km
    (
        "⭐ LÉGENDAIRE ⭐ Voyageur Interstellaire 🛸",
        "Houston, on l’a perdu. Il est beaucoup trop loin. On abandonne le suivi.",
    ),
    # 700 km
    (
        "⭐ LÉGENDAIRE ⭐ Entité Cosmique 🌌",
        "La NASA a annulé un satellite pour te suivre en direct. Budget bien utilisé.",
    ),
    # 720 km
    (
        "⭐ LÉGENDAIRE ⭐ Chuck Norris du Running 🥋",
        "Chuck Norris court derrière TOI. Il essaie de prendre des notes.",
    ),
    # 740 km
    (
        "⭐ LÉGENDAIRE ⭐ Déclaration d’Intention 🏆",
        "Tu ne cours plus. Tu déclares solennellement une intention de te déplacer vite.",
    ),
    # 760 km
    (
        "⭐ LÉGENDAIRE ⭐ Tempête Certifiée 🌩️",
        "Même les jours où tu ne cours pas, le sol tremble par habitude.",
    ),
    # 780 km
    (
        "⭐ LÉGENDAIRE ⭐ Aimant Gravitationnel 🧲",
        "Les kilomètres viennent à toi maintenant. Tu n’as plus à les chercher.",
    ),
    # 800 km
    (
        "⭐ LÉGENDAIRE ⭐ Dieu Vivant du Bitume 👑",
        "Les ronds-points portent ton prénom. Officieusement, mais quand même.",
    ),
    # 820 km
    (
        "⭐ LÉGENDAIRE ⭐ Carburant Illimité ⛽",
        "Les scientifiques veulent étudier ton métabolisme. Elon Musk veut le breveter.",
    ),
    # 840 km
    (
        "⭐ LÉGENDAIRE ⭐ Usine à Records 🏭",
        "Tu produis des km comme d’autres produisent des excuses. Industriellement.",
    ),
    # 860 km
    (
        "⭐ LÉGENDAIRE ⭐ Boss Absolu 👊",
        "La discipline ne te sert plus le café. Elle te demande la permission de te parler.",
    ),
    # 880 km
    (
        "⭐ LÉGENDAIRE ⭐ Collectionneur de Saisons 📅",
        "Tu ne coches plus des cases. Tu remplis des encyclopédies.",
    ),
    # 900 km
    (
        "⭐ MYTHIQUE ⭐ Transcendance Totale 🔮",
        "Tu es devenu quelque chose que la science ne peut pas encore nommer. Les linguistes travaillent dessus.",
    ),
    # 920 km
    (
        "⭐ MYTHIQUE ⭐ Anti-Matière du Sport 🌀",
        "La flemme a non seulement déménagé — elle a changé de planète et coupé le contact.",
    ),
    # 940 km
    (
        "⭐ MYTHIQUE ⭐ Monstre Incompris 🧟",
        "Ton entourage dit ‘mais pourquoi ?’ Tu réponds avec les yeux d’un être supérieur.",
    ),
    # 960 km
    (
        "⭐ MYTHIQUE ⭐ Mythe Vivant 🏛️",
        "On parle de toi au café du coin. Et dans les cafés des coins adjacents.",
    ),
    # 980 km
    (
        "⭐ MYTHIQUE ⭐ Force de la Nature 🌊",
        "Tu n’es plus une personne. Tu es un phénomène météorologique qui court.",
    ),
    # 1000 km
    (
        "☠️ ULTIME LÉGENDAIRE ☠️ 1000 km Accomplis ✅",
        "Les dieux de l’Olympe ont annulé leur abonnement salle de sport par honte. Bravo.",
    ),
]


def get_fun_badge(km: float):
    """Retourne (badge, message) selon les kilomètres."""
    i = 0
    while i < len(BADGE_THRESHOLDS) and km >= BADGE_THRESHOLDS[i]:
        i += 1
    return BADGE_REWARDS[min(i, len(BADGE_REWARDS) - 1)]


def get_badge_progress(km):
    """Retourne (percent, km_restants, prochain_badge_label) ou None si au max."""
    if km >= BADGE_THRESHOLDS[-1]:
        return None
    current_threshold = 0
    next_threshold = BADGE_THRESHOLDS[0]
    for t in BADGE_THRESHOLDS:
        if km >= t:
            current_threshold = t
        else:
            next_threshold = t
            break
    range_km = next_threshold - current_threshold
    progress_km = km - current_threshold
    percent = min(100, max(0, (progress_km / range_km) * 100)) if range_km > 0 else 0
    km_restants = next_threshold - km
    next_badge_label, _ = get_fun_badge(next_threshold)
    return (percent, km_restants, next_badge_label)


def get_denivele_comment(denivele_val: str) -> str:
    """Retourne un commentaire fun sur le dénivelé, ou '' si absent/nul."""
    try:
        d = int(denivele_val or 0)
    except ValueError:
        return ""
    if d <= 0:
        return ""
    if d >= 2000:
        return f"⛰️ {d} m D+ — tu gravis des montagnes !"
    if d >= 1000:
        return f"⛰️ {d} m D+ — impressionnant grimpeur !"
    if d >= 500:
        return f"⛰️ {d} m D+ en prime !"
    return f"⛰️ {d} m D+ au compteur."


def build_teams(participants_sorted):
    """Agrège les participants par équipe et retourne (teams, equipe_members).

    teams: liste de dicts triée par km décroissant
    equipe_members: dict {key_lower: [participants]}
    """
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
    return teams, equipe_members


def compute_awards(participants, teams):
    """Calcule les trophées spéciaux (records individuels et équipe)."""
    awards = []
    hommes = [p for p in participants if p.get("sexe") == "M"]
    femmes = [p for p in participants if p.get("sexe") == "F"]

    # Roi/Reine du Kilomètre
    if hommes:
        best_h = max(hommes, key=km_float)
        awards.append(
            {
                "emoji": "\U0001f3c3",
                "title": "Roi du Kilom\u00e8tre",
                "winner": best_h["nom"],
                "value": f"{best_h['km']} km",
                "detail": "",
            }
        )
    if femmes:
        best_f = max(femmes, key=km_float)
        awards.append(
            {
                "emoji": "\U0001f3c3\u200d\u2640\ufe0f",
                "title": "Reine du Kilom\u00e8tre",
                "winner": best_f["nom"],
                "value": f"{best_f['km']} km",
                "detail": "",
            }
        )

    # Le Plus Régulier / La Plus Régulière
    def seances_int(p):
        try:
            return int(p.get("nb_seances", "0"))
        except ValueError:
            return 0

    if hommes:
        best_h = max(hommes, key=seances_int)
        awards.append(
            {
                "emoji": "\U0001f504",
                "title": "Le Plus R\u00e9gulier",
                "winner": best_h["nom"],
                "value": f"{best_h['nb_seances']} s\u00e9ances",
                "detail": "",
            }
        )
    if femmes:
        best_f = max(femmes, key=seances_int)
        awards.append(
            {
                "emoji": "\U0001f504",
                "title": "La Plus R\u00e9guli\u00e8re",
                "winner": best_f["nom"],
                "value": f"{best_f['nb_seances']} s\u00e9ances",
                "detail": "",
            }
        )

    # Le Grimpeur / La Grimpeuse
    def denivele_int(p):
        try:
            return int(p.get("denivele", "0") or "0")
        except ValueError:
            return 0

    hommes_d = [p for p in hommes if denivele_int(p) > 0]
    femmes_d = [p for p in femmes if denivele_int(p) > 0]
    if hommes_d:
        best_h = max(hommes_d, key=denivele_int)
        awards.append(
            {
                "emoji": "\u26f0\ufe0f",
                "title": "Le Grimpeur Fou",
                "winner": best_h["nom"],
                "value": f"{best_h.get('denivele', '0')} m D+",
                "detail": "",
            }
        )
    if femmes_d:
        best_f = max(femmes_d, key=denivele_int)
        awards.append(
            {
                "emoji": "\u26f0\ufe0f",
                "title": "La Grimpeuse Folle",
                "winner": best_f["nom"],
                "value": f"{best_f.get('denivele', '0')} m D+",
                "detail": "",
            }
        )

    # L'Équipe de Choc (meilleure moyenne km/membre, min 3 membres)
    eligible = [t for t in teams if t["nb_equipier"] >= 3]
    if eligible:
        best_team = max(
            eligible, key=lambda t: float(t["km"].replace(",", ".")) / t["nb_equipier"]
        )
        avg = float(best_team["km"].replace(",", ".")) / best_team["nb_equipier"]
        awards.append(
            {
                "emoji": "\U0001f465",
                "title": "L'\u00c9quipe de Choc",
                "winner": best_team["equipe"],
                "value": f"{avg:.1f} km/membre",
                "detail": f"{best_team['nb_equipier']} \u00e9quipiers",
            }
        )

    return awards


def compute_battles(teams, max_battles=3):
    """Trouve les duels les plus serrés entre équipes consécutives au classement."""
    if len(teams) < 2:
        return []
    pairs = []
    for i in range(len(teams) - 1):
        km1 = float(teams[i]["km"].replace(",", "."))
        km2 = float(teams[i + 1]["km"].replace(",", "."))
        ecart = km1 - km2
        pairs.append(
            {
                "team1": teams[i]["equipe"],
                "team2": teams[i + 1]["equipe"],
                "km1": teams[i]["km"],
                "km2": teams[i + 1]["km"],
                "ecart": f"{ecart:.1f}".replace(".", ","),
            }
        )
    pairs.sort(key=lambda x: float(x["ecart"].replace(",", ".")))
    return pairs[:max_battles]


# Milestones partagés entre generate_html et generate_team_page
JOURNEY_MILESTONES = [
    (
        200,
        "\U0001f1ee\U0001f1f9",
        "Rome (depuis Nice)",
        "Andiamo ! Pasta e basta ! \U0001f35d",
    ),
    (
        800,
        "\U0001f1ec\U0001f1f7",
        "Ath\u00e8nes",
        "Berceau des JO ! On court comme les anciens ! \U0001f3db\ufe0f",
    ),
    (
        1_600,
        "\U0001f1ea\U0001f1f8",
        "Madrid",
        "Ol\u00e9 ! On traverse les Pyr\u00e9n\u00e9es ! \U0001f483",
    ),
    (3_000, "\U0001f1ec\U0001f1e7", "Londres", "Keep calm and keep running ! \u2615"),
    (
        4_000,
        "\U0001f30d",
        "Hors d'Europe",
        "On quitte le continent, adios les boloss, on se casse au soleil ! \u2708\ufe0f",
    ),
    (
        5_500,
        "\U0001f1ea\U0001f1ec",
        "Le Caire",
        "Les pyramides en vue ! Pas le temps de visiter ! \U0001f42a",
    ),
    (
        7_000,
        "\U0001f30d",
        "L'Afrique (cap vers le sud)",
        "Jambo ! Le soleil tape mais on l\u00e2che rien ! \u2600\ufe0f",
    ),
    (
        9_500,
        "\U0001f1e7\U0001f1f7",
        "Rio de Janeiro",
        "Samba et sueur ! Carnaval des mollets ! \U0001f3ad",
    ),
    (
        12_000,
        "\U0001f1fa\U0001f1f8",
        "Les Am\u00e9riques (cap vers l'ouest)",
        "Travers\u00e9e de l'Atlantique ! Bonjour New York ! \U0001f5fd",
    ),
    (
        16_000,
        "\U0001f1f2\U0001f1fd",
        "Mexico",
        "Arriba arriba ! Tacos rechargement ! \U0001f32e",
    ),
    (
        20_000,
        "\U0001f54c",
        "L'Inde (cap vers l'est)",
        "Namaste ! Curry power activated ! \U0001f35b",
    ),
    (
        24_000,
        "\U0001f1f9\U0001f1ed",
        "Bangkok",
        "Pad tha\u00ef et massages pour les mollets ! \U0001f35c",
    ),
    (
        28_000,
        "\U0001f3ef",
        "L'Asie (Japon)",
        "Konnichiwa ! On est \u00e0 l'autre bout du monde ! \U0001f409",
    ),
    (
        32_000,
        "\U0001f1e6\U0001f1fa",
        "Sydney",
        "G'day mate ! Les kangourous nous encouragent ! \U0001f998",
    ),
    # Paliers absurdes 40k-200k
    (40_000, "🌍", "Tour de la Terre", "On est passé voir, elle est toujours ronde."),
    (
        50_000,
        "🔌",
        "Le câble derrière le bureau",
        "Distance estimée entre votre ordinateur et la prise murale la plus proche.",
    ),
    (
        60_000,
        "📱",
        "Scroll nocturne",
        'Distance parcourue par votre pouce à 2h du matin en disant "encore une dernière vidéo".',
    ),
    (
        70_000,
        "⏳",
        "La mise à jour système",
        "Distance parcourue par la barre de progression qui reste bloquée à 99 %.",
    ),
    (
        80_000,
        "🌍🌍",
        "Deuxième tour de la Terre",
        "On commence à reconnaître les nuages.",
    ),
    (
        90_000,
        "🔇",
        "Réunion inutile",
        'Distance mentale parcourue pendant qu\'on cherche le bouton "mute".',
    ),
    (
        100_000,
        "📜",
        "Conditions d'utilisation",
        "Longueur cumulée de tout ce que vous avez accepté sans lire.",
    ),
    (
        110_000,
        "🔑",
        "Mot de passe oublié",
        'Distance entre "je vais m\'en souvenir" et "réinitialiser".',
    ),
    (
        120_000,
        "🔌",
        "Câbles mystérieux",
        'Longueur totale des câbles gardés dans un tiroir "au cas où".',
    ),
    (
        130_000,
        "✅",
        "La TODO list",
        "Distance entre écrire une tâche simple et la faire réellement.",
    ),
    (
        140_000,
        "⚙️",
        "Compilation",
        "Distance parcourue en regardant la console comme si ça allait accélérer.",
    ),
    (
        150_000,
        "📶",
        "Wi-Fi capricieux",
        "Distance entre votre bureau et l'endroit précis où Internet fonctionne.",
    ),
    (
        160_000,
        "🐛",
        "Le bug fantôme",
        'Distance entre "ça marche chez moi" et "ça casse en production".',
    ),
    (
        170_000,
        "💻",
        "Stack Overflow",
        "Distance entre une erreur obscure et un post de 2011 avec la solution.",
    ),
    (
        180_000,
        "⚡",
        "Le commit rapide",
        'Distance entre "petite modification rapide" et trois heures plus tard.',
    ),
    (
        190_000,
        "🔨",
        "Refactorisation",
        'Distance entre "on va nettoyer un peu le code" et réécrire la moitié du projet.',
    ),
    (
        200_000,
        "🌍🌍🌍🌍🌍",
        "Cinq tours de la Terre",
        "À ce stade vous connaissez les continents par cœur.",
    ),
    # Retour aux paliers géographiques
    (
        40_075,
        "\U0001f310",
        "Tour de la Terre (officiel)",
        "Un tour complet du globe ! \U0001f92f",
    ),
    (
        80_000,
        "\U0001f310\U0001f310",
        "2x le tour de la Terre",
        "On repart pour un tour ?! Vous \u00eates malades ! \U0001f92a",
    ),
    (
        384_400,
        "\U0001f319",
        "La Lune",
        "Houston, on a un probl\u00e8me... de motivation ! \U0001f9d1\u200d\U0001f680",
    ),
    (
        225_000_000,
        "\U0001f534",
        "Mars",
        "Mars... Bleu, la plan\u00e8te, vous avez compris le jeu de mots ? \U0001f60f",
    ),
]


def generate_team_page(team, rank, members, is_fun=False):
    """Génère une page HTML autonome pour une équipe du top 5."""
    now = get_paris_time()
    team_name = team["equipe"]
    team_km_str = team["km"]
    team_km = float(team_km_str.replace(",", "."))
    nb_members = team["nb_equipier"]
    slug = slugify(team_name)
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    medal = medals[rank - 1] if rank <= 10 else ""

    esc = html_mod.escape

    # Build member cards
    card_lines = ['<div class="member-cards">']
    for idx, p in enumerate(sorted(members, key=km_float, reverse=True), 1):
        sexe_tag = (
            f'<span class="tag tag-sexe-m">{esc(p["sexe"])}</span>'
            if p["sexe"] == "M"
            else f'<span class="tag tag-sexe-f">{esc(p["sexe"])}</span>'
        )
        cat_tag = f'<span class="tag tag-cat">{esc(cat_fr(p["categorie"]))}</span>'
        denivele_val = p.get("denivele", "")
        denivele_str = f"{esc(denivele_val)} m dénivelé" if denivele_val else ""
        details_parts = [f"{esc(p['nb_seances'])} séances"]
        if denivele_str:
            details_parts.append(denivele_str)
        badge_html = ""
        if is_fun:
            badge_label, badge_motiv = get_fun_badge(km_float(p))
            denivele_comment = get_denivele_comment(denivele_val)
            denivele_html = (
                f'<small class="fun-denivele">{denivele_comment}</small>'
                if denivele_comment
                else ""
            )
            progress = get_badge_progress(km_float(p))
            progress_html = ""
            if progress:
                pct, km_rest, next_badge = progress
                progress_html = (
                    f'<div class="progress-bar-container">'
                    f'<div class="progress-bar" style="width: {pct:.0f}%"></div>'
                    f"</div>"
                    f'<small class="progress-label">Encore {km_rest:.1f} km pour atteindre le niveau {next_badge}</small>'
                )
            badge_html = (
                f'<div class="member-badge">'
                f'<span class="fun-badge">🏅 {badge_label}</span>'
                f'<small class="fun-motivation">{badge_motiv}</small>'
                f"{denivele_html}"
                f"{progress_html}"
                f"</div>"
            )
        border_color = (
            "var(--accent)" if idx > 3 else ["#ffd700", "#c0c0c0", "#cd7f32"][idx - 1]
        )
        card_lines.append(
            f'<div class="member-card" style="border-left: 4px solid {border_color};">'
            f'<div class="member-header">'
            f'<span class="member-rank">#{idx}</span>'
            f'<span class="member-name">{esc(p["nom"])}</span>'
            f'<span class="member-km">{esc(p["km"])} km</span>'
            f"</div>"
            f'<div class="member-details">{" · ".join(details_parts)}</div>'
            f'<div class="member-tags">{sexe_tag} {cat_tag}</div>'
            f"{badge_html}"
            f"</div>"
        )
    card_lines.append("</div>")
    member_table = "\n".join(card_lines)

    # Journey milestones (fun only, filtered)
    journey_html = ""
    if is_fun:
        # Determine which milestones to show:
        # - last reached (as reference)
        # - current in-progress
        # - next 2-3 locked
        last_reached_idx = -1
        for i, (dist, _, _, _) in enumerate(JOURNEY_MILESTONES):
            if team_km >= dist:
                last_reached_idx = i

        passed_steps = []
        filtered = []
        for i, (dist, icon, name, msg) in enumerate(JOURNEY_MILESTONES):
            reached = team_km >= dist
            if reached and i < last_reached_idx:
                # collect passed milestones for collapsible section
                dist_fmt = f"{dist:,}".replace(",", " ")
                passed_steps.append(
                    f'<div class="journey-step reached">'
                    f'<div class="journey-step-header">'
                    f'<span class="journey-icon">{icon}</span>'
                    f'<span class="journey-name">{name}</span>'
                    f'<span class="journey-check">✅</span>'
                    f"</div>"
                    f'<div class="journey-dist">{dist_fmt} km</div>'
                    f'<div class="journey-bar"><div class="journey-bar-fill" style="width:100%"></div></div>'
                    f'<div class="journey-msg">{msg}</div>'
                    f"</div>"
                )
                continue
            if not reached and i > last_reached_idx + 4:
                break  # only show 2-3 locked after in-progress
            if reached:
                pct = 100
            else:
                prev_dist = JOURNEY_MILESTONES[i - 1][0] if i > 0 else 0
                pct = (
                    max(0, min(100, ((team_km - prev_dist) / (dist - prev_dist)) * 100))
                    if team_km > prev_dist
                    else 0
                )
            status_cls = (
                "reached" if reached else ("in-progress" if pct > 0 else "locked")
            )
            check = "✅" if reached else ("🏃" if pct > 0 else "🔒")
            dist_fmt = f"{dist:,}".replace(",", " ")
            filtered.append(
                f'<div class="journey-step {status_cls}">'
                f'<div class="journey-step-header">'
                f'<span class="journey-icon">{icon}</span>'
                f'<span class="journey-name">{name}</span>'
                f'<span class="journey-check">{check}</span>'
                f"</div>"
                f'<div class="journey-dist">{dist_fmt} km</div>'
                f'<div class="journey-bar"><div class="journey-bar-fill" style="width:{pct:.1f}%"></div></div>'
                f'<div class="journey-msg">{msg}</div>'
                f"</div>"
            )
        passed_html = ""
        if passed_steps:
            n = len(passed_steps)
            passed_html = (
                f'<details class="journey-passed">'
                f"<summary>📜 Étapes précédentes ({n} accomplie{'s' if n > 1 else ''})</summary>"
                f'<div class="journey-milestones">{"".join(passed_steps)}</div>'
                f"</details>"
            )
        journey_html = (
            f'<div class="journey-container">'
            f'<h3 class="journey-title">🗺️ Voyage de l\'équipe — {team_km:,.1f} km parcourus</h3>'
            f"{passed_html}"
            f'<div class="journey-milestones">{"".join(filtered)}</div>'
            f"</div>"
        ).replace(",", " ")

    # Rotating motivational quotes (fun only)
    fun_quotes_html = ""
    if is_fun:
        fun_quotes_html = """<div id="fun-quotes" class="fun-quotes-banner">
  <span id="fun-quote-text"></span>
</div>"""

    # Navigation links
    back_link = "fun.html" if is_fun else "index.html"
    back_label = (
        "🤓 Retour au classement" if not is_fun else "🤪 Retour au classement fun"
    )
    switch_fun_link = f"equipe-{slug}-fun.html" if not is_fun else f"equipe-{slug}.html"
    switch_fun_label = "🤪 Version Fun" if not is_fun else "🤓 Version Sérieuse"

    page_title = f"{team_name} — Mars Bleu 2026"
    if is_fun:
        page_title = f"{medal} {team_name} — Bouge Ton Popotin ! 🍑"

    hero_title = f"{medal} {esc(team_name)}"

    fun_css_block = ""
    if is_fun:
        fun_css_block = """<style>
body {
  font-family: 'Comic Sans MS', 'Chalkboard SE', 'Comic Neue', sans-serif !important;
  background-color: var(--fun-bg, #e0f2fe) !important;
  background-image: radial-gradient(var(--fun-dot, #bae6fd) 20%, transparent 20%),
                    radial-gradient(var(--fun-dot, #bae6fd) 20%, transparent 20%) !important;
  background-position: 0 0, 25px 25px !important;
  background-size: 50px 50px !important;
}
[data-theme="dark"] body { --fun-bg: #0f172a; --fun-dot: #1e293b; }
.fun-motivation { color: #e91e63; font-style: italic; font-size: 0.8rem; font-weight: bold; }
.fun-denivele { display: block; color: #10b981; font-size: 0.78rem; font-style: italic; font-weight: 600; margin-top: 0.2rem; line-height: 1.3; word-break: break-word; }
.fun-badge { font-size: 0.85rem !important; display: inline-block; padding: 0.3rem 0.8rem; border-radius: 6px; background: rgba(251, 191, 36, 0.15) !important; color: #fbbf24 !important; font-weight: 600; }
.member-card:hover {
  transform: scale(1.02) rotate(-1deg) !important; transition: transform 0.1s;
}
[data-theme="light"] .journey-container {
  background: linear-gradient(135deg, #ffffff 0%, #f0f4ff 100%);
  box-shadow: 0 4px 20px rgba(0,0,0,0.1); border: 2px solid #e0e7ff;
}
[data-theme="light"] .journey-title { color: #5b21b6; text-shadow: none; }
[data-theme="light"] .journey-name { color: #1e293b; }
[data-theme="light"] .journey-dist { color: #64748b; }
[data-theme="light"] .journey-msg { color: #059669; }
[data-theme="light"] .journey-step { background: rgba(0,0,0,0.03); }
[data-theme="light"] .journey-step.reached { background: rgba(16, 185, 129, 0.1); border-left-color: #10b981; }
[data-theme="light"] .journey-step.in-progress { background: rgba(245, 158, 11, 0.1); border-left-color: #f59e0b; }
[data-theme="light"] .journey-step.locked { background: rgba(0,0,0,0.02); border-left-color: #cbd5e1; }
[data-theme="light"] .journey-bar { background: #e2e8f0; }
[data-theme="light"] .journey-passed summary { color: #5b21b6; }
/* Achievement toast notifications */
.fun-toast {
  position: fixed;
  right: -400px;
  padding: 1rem 1.5rem;
  background: linear-gradient(135deg, #2d3436, #636e72);
  color: white;
  border-radius: 12px;
  border-left: 5px solid #feca57;
  box-shadow: 0 8px 25px rgba(0,0,0,0.4);
  z-index: 9999;
  font-weight: bold;
  font-size: 0.95rem;
  max-width: 350px;
  transition: right 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}
.fun-toast.show {
  right: 20px;
}
/* Progress bar toward next badge */
.progress-bar-container {
  background: #e0e0e0;
  border-radius: 8px;
  height: 8px;
  margin-top: 4px;
  overflow: hidden;
}
[data-theme="dark"] .progress-bar-container {
  background: #374151;
}
.progress-bar {
  background: linear-gradient(90deg, #4CAF50, #8BC34A);
  height: 100%;
  border-radius: 8px;
  transition: width 0.3s;
}
.progress-label {
  font-size: 0.7rem;
  color: #6b7280;
  display: block;
  margin-top: 2px;
}
[data-theme="dark"] .progress-label {
  color: #9ca3af;
}
/* Rotating quotes banner */
.fun-quotes-banner {
  max-width: 800px;
  margin: 0 auto 1rem;
  text-align: center;
  padding: 1.2rem 2rem;
  background: linear-gradient(135deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3);
  background-size: 300% 300%;
  animation: gradient-shift 4s ease infinite;
  border-radius: 16px;
  font-size: 1.3rem;
  font-weight: bold;
  color: #1a1a2e;
  box-shadow: 0 4px 15px rgba(0,0,0,0.2);
  min-height: 3.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
@keyframes gradient-shift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
#fun-quote-text {
  transition: opacity 0.5s ease;
}
[data-theme="light"] .fun-quotes-banner {
  color: #1a1a2e;
}
[data-theme="light"] .fun-toast {
  background: linear-gradient(135deg, #ffffff, #f8fafc);
  color: #1e293b;
  border-left-color: #f59e0b;
}
</style>"""

    fun_script = ""
    if is_fun:
        fun_script = """
<script>
window.addEventListener('load', function() {{
    var allToasts = [
      "\\ud83c\\udfc6 Achievement: Tu as ouvert la page ! +10 points motivation",
      "\\ud83c\\udfc6 Achievement: Stalker de classement d\\u00e9tect\\u00e9 !",
      "\\ud83c\\udfc6 Achievement: Mode Fun activ\\u00e9 ! Tu g\\u00e8res !",
      "\\ud83d\\udc40 Achievement: Espionnage de concurrents en cours...",
      "\\ud83e\\uddb6 Achievement: Tes mollets ont senti ta pr\\u00e9sence",
      "\\ud83c\\udf55 Achievement: Calories brul\\u00e9es = 1 pizza gratuite",
      "\\ud83d\\udca9 Achievement: Tu scrolles au lieu de courir !",
      "\\ud83e\\udd21 Achievement: Fan n\\u00b01 du Mode Fun",
      "\\ud83d\\ude34 Achievement: Le canap\\u00e9 pleure ton absence",
      "\\ud83e\\uddd0 Achievement: Analyse tactique du classement"
    ];
    var toasts = [];
    var indices = [];
    while (toasts.length < 3 && indices.length < allToasts.length) {{
      var ri = Math.floor(Math.random() * allToasts.length);
      if (indices.indexOf(ri) === -1) {{ indices.push(ri); toasts.push(allToasts[ri]); }}
    }}
    function showToast(msg, delay, topOffset) {{
      setTimeout(function() {{
        var t = document.createElement('div');
        t.className = 'fun-toast';
        t.textContent = msg;
        t.style.top = topOffset + 'px';
        document.body.appendChild(t);
        setTimeout(function() {{ t.classList.add('show'); }}, 50);
        setTimeout(function() {{
          t.classList.remove('show');
          setTimeout(function() {{ t.remove(); }}, 600);
        }}, 4000);
      }}, delay);
    }}
    showToast(toasts[0], 3500, 20);
    showToast(toasts[1], 5500, 90);
    showToast(toasts[2], 7500, 160);

    // Rotating motivational quotes
    var quotes = [
      "La sueur, c'est juste tes bourrelets qui pleurent \\ud83d\\ude2d",
      "Cours comme si le dernier pain au chocolat t'attendait \\ud83e\\udd50",
      "Tes fesses te remercieront... un jour \\ud83c\\udf51",
      "On n'est pas l\\u00e0 pour souffrir... ah si en fait \\ud83d\\ude05",
      "Chaque kilom\\u00e8tre te rapproche de Mars ! \\ud83d\\ude80",
      "Le canap\\u00e9 est ton ennemi. Le bitume est ton ami. \\ud83d\\udeb6",
      "T'as pas fait tout \\u00e7a pour abandonner maintenant ! \\ud83d\\udcaa",
      "M\\u00eame un escargot finit par arriver \\ud83d\\udc0c",
      "Ton corps te d\\u00e9teste l\\u00e0, mais il t'aimera demain \\u2764\\ufe0f",
      "Si t'arrives \\u00e0 lire \\u00e7a en courant, ralentis pas ! \\ud83c\\udfc3",
      "Cours plus vite que ta digestion \\ud83d\\udca9"
    ];
    var quoteEl = document.getElementById('fun-quote-text');
    if (quoteEl) {{
      var qi = 0;
      quoteEl.textContent = quotes[0];
      setInterval(function() {{
        quoteEl.style.opacity = '0';
        setTimeout(function() {{
          qi = (qi + 1) % quotes.length;
          quoteEl.textContent = quotes[qi];
          quoteEl.style.opacity = '1';
        }}, 500);
      }}, 4000);
    }}
}});
</script>"""

    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
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
  --bg: #faf8f5; --bg-card: #ffffff; --text: #0a1628; --text-secondary: #4a5568;
  --text-muted: #8e99a9; --border: #e5e1d8; --border-light: #f0ece4;
  --accent: #1a56db; --accent-light: rgba(26,86,219,0.08);
  --hero-from: #0a1628; --hero-via: #112240; --hero-to: #1a56db;
  --tag-m-bg: #dbeafe; --tag-m-text: #1e40af; --tag-f-bg: #fce7f3; --tag-f-text: #be185d;
  --tag-cat-bg: #fef3c7; --tag-cat-text: #92400e; --tag-km-bg: #d1fae5; --tag-km-text: #065f46;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.06); --shadow-md: 0 4px 14px rgba(0,0,0,0.07);
  --radius: 12px; --input-bg: #ffffff; --input-border: #d5d0c8;
  --footer-bg: #faf8f5; --footer-text: #64748b;
}}
[data-theme="dark"] {{
  --bg: #0a1628; --bg-card: #111d32; --text: #e8edf5; --text-secondary: #94a3b8;
  --text-muted: #64748b; --border: #1e3150; --border-light: #162541;
  --accent: #3b82f6; --accent-light: rgba(59,130,246,0.12);
  --hero-from: #020b1a; --hero-via: #0a1628; --hero-to: #1e3a6e;
  --tag-m-bg: #1e3a5f; --tag-m-text: #93c5fd; --tag-f-bg: #4a1942; --tag-f-text: #f9a8d4;
  --tag-cat-bg: #422006; --tag-cat-text: #fcd34d; --tag-km-bg: #064e3b; --tag-km-text: #6ee7b7;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.3); --shadow-md: 0 4px 14px rgba(0,0,0,0.3);
  --input-bg: #111d32; --input-border: #1e3150;
  --footer-bg: #0a1628; --footer-text: #94a3b8;
  --bulma-text-strong: var(--text); --bulma-text: var(--text-secondary);
  --bulma-scheme-main: var(--bg); --bulma-scheme-main-bis: var(--bg-card);
  --bulma-table-color: var(--text); --bulma-table-background-color: var(--bg-card);
  --bulma-table-cell-border-color: var(--border);
  --bulma-body-background-color: var(--bg); --bulma-body-color: var(--text);
  --bulma-strong-color: var(--text);
}}
body {{ background: var(--bg); color: var(--text); font-family: var(--font-body); transition: background 0.3s, color 0.3s; }}
.hero-section {{
  background: linear-gradient(135deg, var(--hero-from) 0%, var(--hero-via) 40%, var(--hero-to) 100%);
  padding: 2rem 1.5rem 1.5rem; text-align: center;
}}
.hero-title {{ font-family: var(--font-heading); font-size: 2rem; font-weight: 900; color: #ffffff; margin: 0 0 0.5rem; }}
.hero-subtitle {{ color: rgba(255,255,255,0.7); font-size: 1rem; }}
.depistage-msg {{ color: #fbbf24; font-family: var(--font-heading); font-size: 1.3rem; font-weight: 700; margin-top: 0.7rem; text-shadow: 0 1px 4px rgba(0,0,0,0.3); }}
.stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: -1.5rem auto 0.5rem; max-width: 700px; padding: 0 1.5rem; position: relative; z-index: 2; }}
.stat-card {{ background: var(--bg-card); border-radius: var(--radius); padding: 0.8rem; text-align: center; box-shadow: var(--shadow-md); border-top: 3px solid var(--accent); }}
.stat-card .stat-value {{ font-family: var(--font-heading); font-size: 2rem; font-weight: 700; color: var(--accent); }}
.stat-card .stat-label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1.5px; color: var(--text-muted); margin-top: 0.3rem; font-weight: 500; }}
.main-content {{ max-width: 1000px; margin: 0 auto; padding: 1rem 1.5rem; }}
.member-cards {{ display: flex; flex-direction: column; gap: 1rem; }}
.member-card {{ background: var(--bg-card); border-radius: var(--radius); padding: 1rem 1.2rem; box-shadow: var(--shadow-sm); border: 1px solid var(--border); transition: transform 0.15s, box-shadow 0.15s; }}
.member-card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-md); }}
.member-header {{ display: flex; align-items: baseline; gap: 0.5rem; margin-bottom: 0.4rem; flex-wrap: wrap; }}
.member-rank {{ font-family: var(--font-heading); font-weight: 700; font-size: 1.1rem; color: var(--text-muted); min-width: 2rem; }}
.member-name {{ font-weight: 700; font-size: 1rem; color: var(--text); flex: 1; }}
.member-km {{ font-weight: 700; font-size: 1.05rem; color: var(--accent); white-space: nowrap; }}
.member-details {{ font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.4rem; }}
.member-tags {{ display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.4rem; }}
.member-badge {{ margin-top: 0.3rem; display: flex; flex-direction: column; gap: 0.2rem; }}
.tag-sexe-m {{ background: var(--tag-m-bg) !important; color: var(--tag-m-text) !important; font-weight: 600; font-size: 0.75rem !important; border-radius: 6px; }}
.tag-sexe-f {{ background: var(--tag-f-bg) !important; color: var(--tag-f-text) !important; font-weight: 600; font-size: 0.75rem !important; border-radius: 6px; }}
.tag-cat {{ background: var(--tag-cat-bg) !important; color: var(--tag-cat-text) !important; font-weight: 500; font-size: 0.75rem !important; border-radius: 6px; }}
.nav-buttons {{ display: flex; gap: 1rem; justify-content: center; margin: 1rem 0; flex-wrap: wrap; }}
.nav-buttons a {{ border-radius: 50px; font-weight: 600; padding: 0.6rem 1.5rem; text-decoration: none; }}
.journey-container {{ max-width: 800px; margin: 0 auto 1rem; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; padding: 1.5rem; box-shadow: 0 8px 25px rgba(0,0,0,0.3); }}
.journey-title {{ text-align: center; font-size: 1.3rem; color: #feca57; margin-bottom: 1rem; text-shadow: 0 0 10px rgba(254, 202, 87, 0.5); }}
.journey-milestones {{ display: flex; flex-direction: column; gap: 0.8rem; }}
.journey-step {{ background: rgba(255,255,255,0.05); border-radius: 12px; padding: 0.8rem 1rem; }}
.journey-step.reached {{ background: rgba(0, 184, 148, 0.15); border-left: 4px solid #00b894; }}
.journey-step.in-progress {{ background: rgba(253, 203, 110, 0.15); border-left: 4px solid #fdcb6e; animation: step-pulse 2s infinite alternate; }}
.journey-step.locked {{ opacity: 0.5; border-left: 4px solid #636e72; }}
@keyframes step-pulse {{ 0% {{ box-shadow: 0 0 5px rgba(253, 203, 110, 0.2); }} 100% {{ box-shadow: 0 0 15px rgba(253, 203, 110, 0.4); }} }}
.journey-step-header {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem; }}
.journey-icon {{ font-size: 1.5rem; }}
.journey-name {{ font-weight: bold; color: #dfe6e9; font-size: 1.05rem; flex: 1; }}
.journey-check {{ font-size: 1.2rem; }}
.journey-dist {{ color: #b2bec3; font-size: 0.85rem; margin-bottom: 0.4rem; }}
.journey-bar {{ height: 10px; background: #2d3436; border-radius: 5px; overflow: hidden; margin-bottom: 0.3rem; }}
.journey-bar-fill {{ height: 100%; background: linear-gradient(90deg, #00b894, #00cec9, #0984e3); border-radius: 5px; transition: width 1.5s ease; }}
.journey-step.reached .journey-bar-fill {{ background: #00b894; }}
.journey-step.in-progress .journey-bar-fill {{ background: linear-gradient(90deg, #fdcb6e, #e17055); }}
.journey-msg {{ color: #81ecec; font-size: 0.85rem; font-style: italic; }}
.journey-step.locked .journey-msg {{ color: #636e72; }}
.journey-passed {{ margin-bottom: 0.8rem; }}
.journey-passed summary {{ cursor: pointer; color: #feca57; font-weight: 600; font-size: 0.95rem; padding: 0.5rem; list-style: none; }}
.journey-passed summary::-webkit-details-marker {{ display: none; }}
.journey-passed summary::before {{ content: "\\25B6  "; font-size: 0.8rem; }}
.journey-passed[open] summary::before {{ content: "\\25BC  "; font-size: 0.8rem; }}
.fab-menu {{ position: fixed; top: 1.5rem; right: 1.5rem; z-index: 1000; display: flex; flex-direction: column; align-items: flex-end; gap: 0.5rem; }}
.fab-btn {{ background: linear-gradient(135deg, var(--accent), var(--accent-dark, var(--accent))); border: none; color: white; width: 3rem; height: 3rem; border-radius: 50%; cursor: pointer; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; box-shadow: var(--shadow-md); transition: all 0.3s ease; }}
.fab-btn:hover {{ transform: scale(1.1); box-shadow: var(--shadow-lg); }}
.fab-dropdown {{ display: none; flex-direction: column; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow-lg); overflow: hidden; min-width: 140px; }}
.fab-dropdown.open {{ display: flex; }}
.fab-item {{ background: none; border: none; color: var(--text); padding: 0.65rem 1rem; cursor: pointer; display: flex; align-items: center; gap: 0.6rem; font-size: 0.9rem; transition: background 0.15s; white-space: nowrap; text-align: left; width: 100%; }}
.fab-item:hover {{ background: var(--bg-hover, rgba(0,0,0,0.06)); }}
.fab-item i {{ width: 1.2rem; text-align: center; color: var(--accent); }}
.video-modal {{ display: none; position: fixed; inset: 0; z-index: 2000; align-items: center; justify-content: center; }}
.video-modal.open {{ display: flex; }}
.video-modal-backdrop {{ position: absolute; inset: 0; background: rgba(0,0,0,0.75); }}
.video-modal-content {{ position: relative; z-index: 1; width: min(360px, 92vw); aspect-ratio: 9 / 16; background: #000; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 40px rgba(0,0,0,0.5); }}
.video-modal-close {{ position: absolute; top: 0.5rem; right: 0.5rem; z-index: 2; background: rgba(0,0,0,0.5); border: none; color: white; width: 2rem; height: 2rem; border-radius: 50%; font-size: 1.2rem; cursor: pointer; display: flex; align-items: center; justify-content: center; line-height: 1; }}
.modal-video {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
/* About Modal */
.about-modal {{ display: none; position: fixed; inset: 0; z-index: 2000; align-items: center; justify-content: center; padding: 1rem; }}
.about-modal.open {{ display: flex; }}
.about-modal-backdrop {{ position: absolute; inset: 0; background: rgba(0,0,0,0.7); }}
.about-modal-content {{ position: relative; background: var(--bg-card, #fff); border-radius: 1rem; padding: 2rem; max-width: 520px; width: 100%; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.3); color: var(--text, #363636); }}
.about-modal-content strong {{ color: var(--text, #363636); }}
.about-modal-close {{ position: absolute; top: 1rem; right: 1rem; background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text, #363636); line-height: 1; }}
.about-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 2px solid #3273dc22; }}
.about-emoji {{ font-size: 2rem; }}
.about-header h2 {{ font-size: 1.25rem; font-weight: 700; color: #3273dc; margin: 0; }}
.about-section {{ margin-bottom: 1.25rem; padding-bottom: 1.25rem; border-bottom: 1px solid rgba(128,128,128,0.15); }}
.about-section:last-of-type {{ border-bottom: none; }}
.about-section h3 {{ font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #3273dc; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }}
.about-section p {{ font-size: 0.92rem; line-height: 1.6; margin: 0; }}
.about-footer {{ margin-top: 1.5rem; text-align: center; }}
.about-link {{ display: inline-flex; align-items: center; gap: 0.5rem; background: #3273dc; color: #fff; padding: 0.6rem 1.2rem; border-radius: 2rem; text-decoration: none; font-size: 0.88rem; font-weight: 600; transition: background 0.2s; }}
.about-link:hover {{ background: #2366d1; color: #fff; }}
.site-footer {{ background: var(--footer-bg); color: var(--footer-text); padding: 2rem; margin-top: 1.5rem; border-top: 2px solid var(--border); font-size: 0.85rem; text-align: center; }}
.site-footer a {{ color: var(--accent); text-decoration: none; }}
@media (max-width: 768px) {{
  .stats-grid {{ grid-template-columns: 1fr; }}
  .hero-title {{ font-size: 1.5rem; }}
}}
</style>
{fun_css_block}
</head>
<body>

<div class="fab-menu" id="fab-menu">
  <button class="fab-btn" id="fab-toggle" aria-expanded="false" title="Menu">
    <i class="fas fa-bars"></i>
  </button>
  <div class="fab-dropdown" id="fab-dropdown">
    <button class="fab-item" id="theme-toggle">
      <i class="fas fa-moon"></i><span>Thème</span>
    </button>
    <button class="fab-item" id="help-btn">
      <i class="fas fa-question-circle"></i><span>Aide</span>
    </button>
    <button class="fab-item" id="about-btn" aria-label="À propos">
      <i class="fas fa-circle-info"></i>
      <span>À propos</span>
    </button>
  </div>
</div>

<div class="video-modal" id="video-modal">
  <div class="video-modal-backdrop" id="video-modal-backdrop"></div>
  <div class="video-modal-content">
    <button class="video-modal-close" id="video-modal-close">&times;</button>
    <video controls preload="none" class="modal-video" id="modal-video">
      <source src="{SUBSCRIBE_VIDEO_URL}" type="video/mp4">
    </video>
  </div>
</div>

<div class="about-modal" id="about-modal">
  <div class="about-modal-backdrop" id="about-modal-backdrop"></div>
  <div class="about-modal-content">
    <button class="about-modal-close" id="about-modal-close">&times;</button>
    <div class="about-header">
      <span class="about-emoji">🩵</span>
      <h2>À propos du Défi Mars Bleu</h2>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-person-running"></i> Le Défi</h3>
      <p>Durant tout le mois de mars, des milliers de courageux chaussent leurs baskets —
        ou enfilent leurs chaussons — pour accumuler des kilomètres ensemble.
        Marche, course, vélo, natation : tout compte !<br><br>
        L'objectif ? Bouger, se connecter, et prouver qu'on peut sauver des vies
        en sueur et en bonne humeur. Parce que rester assis sur son canapé n'a
        jamais guéri personne (médicalement parlant).</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-ribbon"></i> Le Cancer Colorectal : Les Chiffres qui Piquent</h3>
      <p>2ème cancer le plus fréquent en France. 1 personne sur 17 sera concernée
        un jour dans sa vie. Chaque année, plus de 43 000 nouveaux cas diagnostiqués.<br><br>
        La bonne nouvelle ? Dépisté tôt, il se guérit dans <strong>9 cas sur 10</strong>.
        Oui, vous avez bien lu. Neuf sur dix. Votre côlon mérite qu'on s'y intéresse.</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-circle-check"></i> Pourquoi Se Dépister ?</h3>
      <p>À partir de 50 ans (et jusqu'à 74 ans), le test de dépistage est
        <strong>gratuit, discret et réalisable chez soi</strong>. Pas d'excuse !<br><br>
        Demandez votre kit à votre médecin traitant et rejoignez le camp
        des gens qui prennent soin d'eux. Votre famille vous en remerciera.
        Votre côlon aussi, même s'il est pudique.</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-rotate"></i> Comment ça marche ?</h3>
      <p>Ce site est généré automatiquement depuis les données <strong>ZapSport</strong>
        et se rafraîchit toutes les <strong>10 minutes</strong>.<br><br>
        Pour que vos kilomètres apparaissent ici, pensez à
        <strong>télécharger vos parcours sur ZapSport</strong> — sans ça, on ne peut
        pas les comptabiliser. Votre GPS mérite d'être entendu !</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-user-plus"></i> S'inscrire au Défi</h3>
      <p>Pas encore inscrit ? Les inscriptions se font directement en ligne —
        rejoignez les équipes et commencez à accumuler des kilomètres pour la bonne cause !</p>
      <div style="margin-top:0.75rem; text-align:center;">
        <a href="https://www.sport-up.fr/www/inscription_en_ligne_2.0/inscription-39684-ORG-JAVGH.htm"
           target="_blank" rel="noopener" class="about-link" style="font-size:0.82rem;">
          <i class="fas fa-arrow-up-right-from-square"></i>
          S'inscrire sur sport-up.fr
        </a>
      </div>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-heart"></i> Réalisé par</h3>
      <p>Ce site a été concocté par
        <a href="https://www.instagram.com/samchmou/" target="_blank" rel="noopener">@samchmou</a> des
        <a href="https://www.instagram.com/nicerunners06/" target="_blank" rel="noopener">@nicerunners</a>
        pour aider à la motivation des équipes —
        parce qu'un tableau de bord bien visible, ça donne des ailes
        (ou au moins des jambes).</p>
    </div>
    <div class="about-footer">
      <a href="https://www.marsbleuconnecte.fr/#top" target="_blank" rel="noopener" class="about-link">
        <i class="fas fa-arrow-up-right-from-square"></i>
        En savoir plus sur marsbleuconnecte.fr
      </a>
    </div>
  </div>
</div>

<div class="hero-section">
  <a href="https://www.marsbleuconnecte.fr/#top" target="_blank" title="Aller au site Mars Bleu Connecté">
   <img src="{LOGO_URL}" alt="Mars Bleu" class="hero-logo">
  </a>
  <h1 class="hero-title">{hero_title}</h1>
  <p class="hero-subtitle">Équipe classée #{rank} &mdash; Mise à jour : {now}</p>
  <p class="depistage-msg">À partir de 50 ans, je me fais dépister !</p>
</div>

<div class="stats-grid">
  <div class="stat-card">
    <div><div class="stat-value">{team_km_str}</div><div class="stat-label">Kilomètres</div></div>
  </div>
  <div class="stat-card">
    <div><div class="stat-value">{nb_members}</div><div class="stat-label">Équipiers</div></div>
  </div>
  <div class="stat-card">
    <div><div class="stat-value">#{rank}</div><div class="stat-label">Classement</div></div>
  </div>
</div>

<div class="main-content">
  <div class="nav-buttons">
    <a href="{back_link}" class="button is-info is-rounded">{back_label}</a>
    <a href="{switch_fun_link}" class="button is-warning is-rounded">{switch_fun_label}</a>
  </div>

  {fun_quotes_html}

  {journey_html}

  <h2 style="font-family:var(--font-heading);font-size:1.4rem;margin-bottom:1rem;">Membres de l'équipe</h2>
  {member_table}
</div>

<footer class="site-footer">
  <p>
    <span class="footer-brand">Défi Mars Bleu Connecté 2026</span> &mdash;
    Page équipe générée automatiquement
  </p>
  <div class="footer-refresh">
    <span class="footer-refresh-text">
      <i class="fas fa-sync footer-refresh-icon"></i>
      Données mises à jour automatiquement toutes les 10 minutes
    </span>
    <span class="footer-refresh-timestamp">
      Dernière mise à jour : {now}
    </span>
  </div>
</footer>

<script>
// FAB menu
(function() {{
  var html = document.documentElement;
  var fabToggle = document.getElementById('fab-toggle');
  var fabDropdown = document.getElementById('fab-dropdown');
  var themeToggle = document.getElementById('theme-toggle');
  var helpBtn = document.getElementById('help-btn');
  var videoModal = document.getElementById('video-modal');
  var videoModalClose = document.getElementById('video-modal-close');
  var videoModalBackdrop = document.getElementById('video-modal-backdrop');
  var modalVideo = document.getElementById('modal-video');
  var aboutBtn = document.getElementById('about-btn');
  var aboutModal = document.getElementById('about-modal');
  var aboutModalClose = document.getElementById('about-modal-close');
  var aboutModalBackdrop = document.getElementById('about-modal-backdrop');

  // Theme init
  var saved = localStorage.getItem('theme');
  var theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  html.setAttribute('data-theme', theme);
  updateThemeIcon(theme);

  function updateThemeIcon(t) {{
    var icon = themeToggle.querySelector('i');
    icon.className = t === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
  }}

  // FAB open/close
  fabToggle.addEventListener('click', function(e) {{
    e.stopPropagation();
    var open = fabDropdown.classList.toggle('open');
    fabToggle.setAttribute('aria-expanded', open);
  }});
  document.addEventListener('click', function() {{
    fabDropdown.classList.remove('open');
    fabToggle.setAttribute('aria-expanded', false);
  }});

  // Theme toggle
  themeToggle.addEventListener('click', function() {{
    var cur = html.getAttribute('data-theme');
    var nxt = cur === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', nxt);
    localStorage.setItem('theme', nxt);
    updateThemeIcon(nxt);
    fabDropdown.classList.remove('open');
  }});

  // Help → open video modal
  helpBtn.addEventListener('click', function() {{
    videoModal.classList.add('open');
    fabDropdown.classList.remove('open');
  }});

  // About modal
  aboutBtn.addEventListener('click', function() {{
    aboutModal.classList.add('open');
    fabDropdown.classList.remove('open');
    fabToggle.setAttribute('aria-expanded', 'false');
  }});
  [aboutModalClose, aboutModalBackdrop].forEach(function(el) {{
    el.addEventListener('click', function() {{ aboutModal.classList.remove('open'); }});
  }});

  function closeModal() {{
    videoModal.classList.remove('open');
    modalVideo.pause();
  }}
  videoModalClose.addEventListener('click', closeModal);
  videoModalBackdrop.addEventListener('click', closeModal);
}})();
</script>
{fun_script}
</body>
</html>"""


def generate_html(participants, is_fun=False):
    """Génère le fichier HTML avec Bulma (mode standard ou fun)."""
    now = get_paris_time()
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
            "<th>Badge 🏅</th>" if is_fun else "",
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
            if is_fun:
                badge_label, badge_motiv = get_fun_badge(km_float(p))
                denivele_val = p.get("denivele", "")
                denivele_comment = get_denivele_comment(denivele_val)
                denivele_html = (
                    f'<br><small class="fun-denivele">{denivele_comment}</small>'
                    if denivele_comment
                    else ""
                )
                progress = get_badge_progress(km_float(p))
                progress_html = ""
                if progress:
                    pct, km_rest, next_badge = progress
                    progress_html = (
                        f'<div class="progress-bar-container">'
                        f'<div class="progress-bar" style="width: {pct:.0f}%"></div>'
                        f"</div>"
                        f'<small class="progress-label">Encore {km_rest:.1f} km pour atteindre le niveau {next_badge}</small>'
                    )
                lines.append(
                    f'<td data-label="Badge"><span class="tag is-warning is-light fun-badge">{badge_label}</span>'
                    f'<br><small class="fun-motivation">{badge_motiv}</small>'
                    f"{denivele_html}"
                    f"{progress_html}</td>"
                )
            lines.append("</tr>")
        lines.append("</tbody></table>")
        return "\n".join(lines)

    # Onglet Général
    tab_general = render_table(participants_sorted, "table-general")

    # Onglet Par Équipe — build teams from participant data
    teams, equipe_members = build_teams(participants_sorted)
    nb_equipes = len(teams)

    # Team podium for fun mode (top 5 teams, show 3 at a time with rotation)
    team_podium_html = ""
    if is_fun and len(teams) >= 3:
        top_n = min(len(teams), 5)
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        podium_colors = ["#FFD700", "#C0C0C0", "#CD7F32", "#48dbfb", "#ff9ff3"]
        team_entries = ""
        for i in range(top_n):
            t = teams[i]
            display = "flex" if i < 3 else "none"
            team_entries += (
                f'<div class="team-podium-entry team-podium-{i + 1}" data-index="{i}" style="display:{display}">'
                f'<span class="podium-medal">{medals[i]}</span>'
                f'<span class="podium-name" style="color: {podium_colors[i]}">{esc(t["equipe"])}</span>'
                f'<span class="podium-km">{esc(t["km"])} km</span>'
                f'<span class="podium-count">{t["nb_equipier"]} équipiers</span>'
                f"</div>"
            )
        team_podium_html = (
            f'<div class="fun-team-podium" id="fun-team-podium">'
            f'<h3 class="fun-podium-title">🏆 Le Podium des Meutes 🏆</h3>'
            f'<div class="team-podium-entries">{team_entries}</div>'
            f"</div>"
        )

    # Awards and Battles for fun mode
    awards_html = ""
    battles_html = ""
    if is_fun:
        awards = compute_awards(participants_sorted, teams)
        if awards:
            award_cards = ""
            for a in awards:
                detail_line = (
                    f'<div class="award-detail">{esc(a["detail"])}</div>'
                    if a["detail"]
                    else ""
                )
                award_cards += (
                    f'<div class="award-card">'
                    f'<div class="award-emoji">{a["emoji"]}</div>'
                    f'<div class="award-title">{esc(a["title"])}</div>'
                    f'<div class="award-winner">{esc(a["winner"])}</div>'
                    f'<div class="award-value">{esc(a["value"])}</div>'
                    f"{detail_line}"
                    f"</div>"
                )
            awards_html = (
                f'<div class="awards-section">'
                f'<h3 class="awards-title">\U0001f3c6 Tableau d\'Honneur \U0001f3c6</h3>'
                f'<div class="awards-grid">{award_cards}</div>'
                f"</div>"
            )

        battles = compute_battles(teams)
        if battles:
            battle_cards = ""
            for b in battles:
                battle_cards += (
                    f'<div class="battle-card">'
                    f'<span class="battle-team">{esc(b["team1"])} ({esc(b["km1"])} km)</span>'
                    f'<span class="battle-vs">\u26a1 VS \u26a1</span>'
                    f'<span class="battle-team">{esc(b["team2"])} ({esc(b["km2"])} km)</span>'
                    f'<div class="battle-ecart">Seulement {esc(b["ecart"])} km d\'\u00e9cart !</div>'
                    f"</div>"
                )
            battles_html = (
                f'<div class="battles-section">'
                f'<h3 class="battles-title">\u2694\ufe0f Les Battles du Moment \u2694\ufe0f</h3>'
                f'<div class="battles-list">{battle_cards}</div>'
                f"</div>"
            )

    suffix = "-fun" if is_fun else ""
    tab_equipe_parts = []
    for idx, t in enumerate(teams, 1):
        team_slug = slugify(t["equipe"])
        members = equipe_members.get(t["equipe"].lower(), [])
        team_page_link = ""
        if idx <= 10:
            team_page_link = (
                f' <a href="equipe-{team_slug}{suffix}.html" class="tag tag-km" '
                f'style="text-decoration:none;margin-left:0.5rem;" '
                f'onclick="event.stopPropagation()" title="Page dédiée de l\'équipe">'
                f'<i class="fas fa-external-link-alt"></i> Voir la page</a>'
            )
        tab_equipe_parts.append(
            f'<div class="equipe-block" id="equipe-{team_slug}">'
            f'<div class="equipe-summary" onclick="toggleEquipe(this)">'
            f'<span class="equipe-rank">{idx}</span>'
            f'<span class="equipe-name">{esc(t["equipe"])}</span>'
            f'<span class="equipe-tags">'
            f'<span class="tag tag-km">{esc(t["km"])} km</span>'
            f'<span class="tag tag-count">{t["nb_equipier"]} équipiers</span>'
            f"{team_page_link}"
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

    page_title = (
        "Défi Mars Bleu Connecté 2026 - Résultats"
        if not is_fun
        else "Mars Bleu : Opération Bouge Ton Popotin ! 🍑🚀"
    )
    hero_title_html = (
        'Défi <span class="hero-highlight">Mars Bleu</span> Connecté 2026'
        if not is_fun
        else 'Opération <span class="hero-highlight">Bouge Ton Popotin</span> 2026 🍑🚀'
    )
    hero_subtitle = (
        f"Résultats en direct &mdash; Mise à jour : {now}"
        if not is_fun
        else f"On se bouge pour se faire dépister ! &mdash; Maj: {now}"
    )

    total_participants_label = "Participants" if not is_fun else "Fessiers en action 🍑"
    total_km_label = "Kilomètres" if not is_fun else "Kilomètres (vers Mars 🛸)"
    nb_equipes_label = "Équipes" if not is_fun else "Meutes Enragées 🐺"

    switch_link = (
        '<div style="margin-top: 1rem;"><a href="fun.html" class="button is-warning is-rounded">🤪 Mode Fun</a></div>'
        if not is_fun
        else '<div style="margin-top: 1rem;"><a href="index.html" class="button is-info is-rounded">🤓 Retour au Mode Sérieux</a></div>'
    )

    fun_stats = ""
    if is_fun:
        baguettes = int(total_km * 1538)
        pizzas = int(total_km * 3333)  # ~30cm diameter
        bieres = int(total_km * 4545)  # ~22cm height
        croissants = int(total_km * 5882)  # ~17cm
        saucissons = int(total_km * 4000)  # ~25cm
        camemberts = int(total_km * 9091)  # ~11cm
        frites = int(total_km * 14286)  # ~7cm
        # Journey milestones (from Nice)
        milestones = JOURNEY_MILESTONES

        # Build journey milestones HTML
        # Find last reached milestone index
        last_reached_idx = -1
        for i, (dist, _, _, _) in enumerate(milestones):
            if total_km >= dist:
                last_reached_idx = i

        passed_steps = []
        journey_steps = []
        current_milestone_msg = ""
        for i, (dist, icon, name, msg) in enumerate(milestones):
            reached = total_km >= dist
            if reached:
                pct = 100
                current_milestone_msg = msg
            else:
                prev_dist = 0
                for pd, _, _, _ in milestones:
                    if pd < dist:
                        prev_dist = pd
                pct = (
                    max(
                        0, min(100, ((total_km - prev_dist) / (dist - prev_dist)) * 100)
                    )
                    if total_km > prev_dist
                    else 0
                )
            status_cls = (
                "reached" if reached else ("in-progress" if pct > 0 else "locked")
            )
            check = "✅" if reached else ("🏃" if pct > 0 else "🔒")
            dist_fmt = f"{dist:,}".replace(",", " ")
            step_html = (
                f'<div class="journey-step {status_cls}">'
                f'<div class="journey-step-header">'
                f'<span class="journey-icon">{icon}</span>'
                f'<span class="journey-name">{name}</span>'
                f'<span class="journey-check">{check}</span>'
                f"</div>"
                f'<div class="journey-dist">{dist_fmt} km</div>'
                f'<div class="journey-bar"><div class="journey-bar-fill" style="width:{pct:.1f}%"></div></div>'
                f'<div class="journey-msg">{msg}</div>'
                f"</div>"
            )
            if reached and i < last_reached_idx:
                passed_steps.append(step_html)
            else:
                journey_steps.append(step_html)
        if not current_milestone_msg:
            current_milestone_msg = "C'est parti de Nice ! On lace les baskets ! 👟"
        passed_html = ""
        if passed_steps:
            n = len(passed_steps)
            passed_html = (
                f'<details class="journey-passed">'
                f"<summary>📜 Étapes précédentes ({n} accomplie{'s' if n > 1 else ''})</summary>"
                f'<div class="journey-milestones">{"".join(passed_steps)}</div>'
                f"</details>"
            )
        journey_html = (
            f'<div class="journey-container">'
            f'<h3 class="journey-title">🗺️ Le Voyage depuis Nice — {total_km:,.1f} km parcourus</h3>'
            f'<div class="journey-current-msg">{current_milestone_msg}</div>'
            f"{passed_html}"
            f'<div class="journey-milestones">{"".join(journey_steps)}</div>'
            f"</div>"
        ).replace(",", " ")

        # Top 3 for podium
        top3 = (
            participants_sorted[:3]
            if len(participants_sorted) >= 3
            else participants_sorted
        )
        podium_html = ""
        medals = ["🥇", "🥈", "🥉"]
        podium_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]
        for i, p in enumerate(top3):
            podium_html += (
                f'<div class="podium-entry podium-{i + 1}">'
                f'<span class="podium-medal">{medals[i]}</span>'
                f'<span class="podium-name" style="color: {podium_colors[i]}">{esc(p["nom"])}</span>'
                f'<span class="podium-km">{esc(p["km"])} km</span>'
                f'<span class="podium-clap">👏👏👏</span>'
                f"</div>"
            )

        fun_stats = f"""<div class="notification is-info is-light" id="fun-food-facts" style="max-width: 800px; margin: 0 auto 1rem; text-align: center; border-radius: 12px; font-weight: bold; font-size: 1.1rem;">
  <span id="fun-food-text">🥖 Déjà l'équivalent de {baguettes:,} baguettes mises bout à bout ! 💪</span>
</div>
<script>
(function() {{
  var foodFacts = [
    "🥖 Déjà l'équivalent de {baguettes:,} baguettes mises bout à bout ! 💪",
    "🍕 Soit {pizzas:,} pizzas alignées les unes à côté des autres ! 🤤",
    "🍺 Ou encore {bieres:,} canettes de bière empilées ! 🍻",
    "🥐 C'est aussi {croissants:,} croissants mis bout à bout ! 🇫🇷",
    "🥖 Ça fait {saucissons:,} saucissons en file indienne ! 😋",
    "🧀 Pas moins de {camemberts:,} camemberts roulés ! 🫠",
    "🍟 Et même {frites:,} frites alignées ! 🤯"
  ];
  var foodEl = document.getElementById('fun-food-text');
  if (foodEl) {{
    var fi = 0;
    setInterval(function() {{
      foodEl.style.opacity = '0';
      foodEl.style.transition = 'opacity 0.5s';
      setTimeout(function() {{
        fi = (fi + 1) % foodFacts.length;
        foodEl.textContent = foodFacts[fi];
        foodEl.style.opacity = '1';
      }}, 500);
    }}, 4000);
  }}
}})();
</script>

<!-- Rotating motivational quotes -->
<div id="fun-quotes" class="fun-quotes-banner">
  <span id="fun-quote-text"></span>
</div>

<!-- Journey milestones from Nice -->
{journey_html}

<!-- Animated podium -->
<div class="fun-podium">
  <h3 class="fun-podium-title">🏆 Le Podium des Machines 🏆</h3>
  <div class="podium-entries">
    {podium_html}
  </div>
  <div class="standing-ovation" id="standing-ovation">👏🎉👏🎉👏🎉👏</div>
</div>
""".replace(",", " ")  # noqa: E501

    fun_css = ""
    if is_fun:
        fun_css = """
<style>
/* 🤪 WILD MODE CSS OVERRIDES 🤪 */
body {
  font-family: 'Comic Sans MS', 'Chalkboard SE', 'Comic Neue', sans-serif !important;
  background-color: var(--fun-bg, #e0f2fe) !important;
  background-image: radial-gradient(var(--fun-dot, #bae6fd) 20%, transparent 20%),
                    radial-gradient(var(--fun-dot, #bae6fd) 20%, transparent 20%) !important;
  background-position: 0 0, 25px 25px !important;
  background-size: 50px 50px !important;
}
[data-theme="dark"] body {
  --fun-bg: #0f172a;
  --fun-dot: #1e293b;
}
/* Light mode fun fixes */
[data-theme="light"] .journey-container {
  background: linear-gradient(135deg, #ffffff 0%, #f0f4ff 100%);
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  border: 2px solid #e0e7ff;
}
[data-theme="light"] .journey-title {
  color: #5b21b6;
  text-shadow: none;
}
[data-theme="light"] .journey-current-msg {
  color: #7c3aed;
}
[data-theme="light"] .journey-name {
  color: #1e293b;
}
[data-theme="light"] .journey-dist {
  color: #64748b;
}
[data-theme="light"] .journey-msg {
  color: #059669;
}
[data-theme="light"] .journey-step {
  background: rgba(0,0,0,0.03);
}
[data-theme="light"] .journey-step.reached {
  background: rgba(16, 185, 129, 0.1);
  border-left-color: #10b981;
}
[data-theme="light"] .journey-step.in-progress {
  background: rgba(245, 158, 11, 0.1);
  border-left-color: #f59e0b;
}
[data-theme="light"] .journey-step.locked {
  background: rgba(0,0,0,0.02);
  border-left-color: #cbd5e1;
}
[data-theme="light"] .journey-step.locked .journey-msg {
  color: #94a3b8;
}
[data-theme="light"] .journey-bar {
  background: #e2e8f0;
}
[data-theme="light"] .journey-passed summary {
  color: #5b21b6;
}
[data-theme="light"] .fun-podium {
  background: linear-gradient(135deg, #ffffff 0%, #fef3c7 100%);
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  border: 2px solid #fde68a;
}
[data-theme="light"] .fun-podium-title {
  color: #b45309;
  text-shadow: none;
}
[data-theme="light"] .podium-entry {
  background: rgba(0,0,0,0.03);
}
[data-theme="light"] .podium-km {
  color: #475569;
}
[data-theme="light"] .fun-quotes-banner {
  color: #1a1a2e;
}
[data-theme="light"] .notification.is-info.is-light {
  background-color: #dbf4ff !important;
  color: #1a1a2e !important;
}
[data-theme="light"] .fun-toast {
  background: linear-gradient(135deg, #ffffff, #f8fafc);
  color: #1e293b;
  border-left-color: #f59e0b;
  box-shadow: 0 8px 25px rgba(0,0,0,0.15);
}
.site-footer {
  background: linear-gradient(135deg, var(--hero-from) 0%, var(--hero-via) 40%, var(--hero-to) 100%) !important;
  color: rgba(255,255,255,0.7) !important;
  border-top: none !important;
}
.site-footer .footer-brand, .site-footer a {
  color: #ffffff !important;
}
.stat-card {
  animation: bounce 1s infinite alternate !important;
  border: 4px dashed #ff00ff !important;
  transform-origin: bottom;
  opacity: 1 !important;
}
.stat-card:nth-child(2) { animation-delay: 0.2s !important; border-color: #00ff00 !important; }
.stat-card:nth-child(3) { animation-delay: 0.4s !important; border-color: #00ffff !important; }
@keyframes bounce {
  0% { transform: translateY(0) rotate(0deg); }
  100% { transform: translateY(-15px) rotate(2deg); }
}
.participant-row:hover {
  transform: scale(1.02) rotate(-1deg);
  transition: transform 0.1s;
}
.button.is-info, .button.is-warning {
  animation: pulse-button 0.5s infinite alternate !important;
  font-size: 1.2rem !important;
  border: 3px solid #000 !important;
}
@keyframes pulse-button {
  0% { transform: scale(1); background-color: #ff00ff; color: white; }
  100% { transform: scale(1.1); background-color: #00ffff; color: black; }
}
.main-content {
  background: var(--bg-card);
  border-radius: 20px;
  box-shadow: 0 0 30px rgba(0,0,0,0.3);
}
/* Badge motivation text */
.fun-motivation {
  color: #e91e63;
  font-style: italic;
  font-size: 0.8rem;
  font-weight: bold;
}
.fun-denivele {
  display: block;
  color: #10b981;
  font-size: 0.78rem;
  font-style: italic;
  font-weight: 600;
  margin-top: 0.2rem;
  line-height: 1.3;
  word-break: break-word;
}
.fun-badge {
  font-size: 0.85rem !important;
}
/* Rotating quotes banner */
.fun-quotes-banner {
  max-width: 800px;
  margin: 0 auto 1rem;
  text-align: center;
  padding: 1.2rem 2rem;
  background: linear-gradient(135deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3);
  background-size: 300% 300%;
  animation: gradient-shift 4s ease infinite;
  border-radius: 16px;
  font-size: 1.3rem;
  font-weight: bold;
  color: #1a1a2e;
  box-shadow: 0 4px 15px rgba(0,0,0,0.2);
  min-height: 3.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
@keyframes gradient-shift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
#fun-quote-text {
  transition: opacity 0.5s ease;
}
/* Journey milestones */
.journey-container {
  max-width: 800px;
  margin: 0 auto 1rem;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 8px 25px rgba(0,0,0,0.3);
}
.journey-title {
  text-align: center;
  font-size: 1.4rem;
  color: #feca57;
  margin-bottom: 0.5rem;
  text-shadow: 0 0 10px rgba(254, 202, 87, 0.5);
}
.journey-current-msg {
  text-align: center;
  font-size: 1.1rem;
  color: #48dbfb;
  margin-bottom: 1.2rem;
  font-style: italic;
}
.journey-milestones {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}
.journey-step {
  background: rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 0.8rem 1rem;
  transition: transform 0.2s;
}
.journey-step.reached {
  background: rgba(0, 184, 148, 0.15);
  border-left: 4px solid #00b894;
}
.journey-step.in-progress {
  background: rgba(253, 203, 110, 0.15);
  border-left: 4px solid #fdcb6e;
  animation: step-pulse 2s infinite alternate;
}
.journey-step.locked {
  opacity: 0.5;
  border-left: 4px solid #636e72;
}
@keyframes step-pulse {
  0% { box-shadow: 0 0 5px rgba(253, 203, 110, 0.2); }
  100% { box-shadow: 0 0 15px rgba(253, 203, 110, 0.4); }
}
.journey-step-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.3rem;
}
.journey-icon {
  font-size: 1.5rem;
}
.journey-name {
  font-weight: bold;
  color: #dfe6e9;
  font-size: 1.05rem;
  flex: 1;
}
.journey-check {
  font-size: 1.2rem;
}
.journey-dist {
  color: #b2bec3;
  font-size: 0.85rem;
  margin-bottom: 0.4rem;
}
.journey-bar {
  height: 10px;
  background: #2d3436;
  border-radius: 5px;
  overflow: hidden;
  margin-bottom: 0.3rem;
}
.journey-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #00b894, #00cec9, #0984e3);
  border-radius: 5px;
  transition: width 1.5s ease;
}
.journey-step.reached .journey-bar-fill {
  background: #00b894;
}
.journey-step.in-progress .journey-bar-fill {
  background: linear-gradient(90deg, #fdcb6e, #e17055);
}
.journey-msg {
  color: #81ecec;
  font-size: 0.85rem;
  font-style: italic;
}
.journey-step.locked .journey-msg {
  color: #636e72;
}
.journey-passed { margin-bottom: 0.8rem; }
.journey-passed summary { cursor: pointer; color: #feca57; font-weight: 600; font-size: 0.95rem; padding: 0.5rem; list-style: none; }
.journey-passed summary::-webkit-details-marker { display: none; }
.journey-passed summary::before { content: "\\25B6  "; font-size: 0.8rem; }
.journey-passed[open] summary::before { content: "\\25BC  "; font-size: 0.8rem; }
@media (max-width: 600px) {
  .journey-container { padding: 1rem; }
  .journey-step { padding: 0.6rem; }
}
/* Fun podium */
.fun-podium {
  max-width: 800px;
  margin: 0 auto 1rem;
  text-align: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 8px 25px rgba(0,0,0,0.3);
}
.fun-podium-title {
  font-size: 1.5rem;
  color: #feca57;
  margin-bottom: 1rem;
  text-shadow: 0 0 10px rgba(254, 202, 87, 0.5);
}
.podium-entries {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}
.podium-entry {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  padding: 1rem;
  border-radius: 12px;
  background: rgba(255,255,255,0.05);
  min-width: 150px;
}
.podium-1 { animation: podium-glow-gold 1.5s infinite alternate; }
.podium-2 { animation: podium-glow-silver 1.5s infinite alternate; }
.podium-3 { animation: podium-glow-bronze 1.5s infinite alternate; }
@keyframes podium-glow-gold {
  0% { box-shadow: 0 0 5px #FFD700; }
  100% { box-shadow: 0 0 25px #FFD700, 0 0 50px rgba(255,215,0,0.3); }
}
@keyframes podium-glow-silver {
  0% { box-shadow: 0 0 5px #C0C0C0; }
  100% { box-shadow: 0 0 20px #C0C0C0; }
}
@keyframes podium-glow-bronze {
  0% { box-shadow: 0 0 5px #CD7F32; }
  100% { box-shadow: 0 0 20px #CD7F32; }
}
/* Team podium carousel */
.fun-team-podium {
  max-width: 800px;
  margin: 0 auto 1rem;
  text-align: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 8px 25px rgba(0,0,0,0.3);
}
.team-podium-entries {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}
.team-podium-entry {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  padding: 1rem;
  border-radius: 12px;
  background: rgba(255,255,255,0.05);
  min-width: 150px;
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.team-podium-1 { animation: podium-glow-gold 1.5s infinite alternate; }
.team-podium-2 { animation: podium-glow-silver 1.5s infinite alternate; }
.team-podium-3 { animation: podium-glow-bronze 1.5s infinite alternate; }
.podium-count {
  color: #81ecec;
  font-size: 0.85rem;
  font-style: italic;
}
[data-theme="light"] .fun-team-podium {
  background: linear-gradient(135deg, #ffffff 0%, #fef3c7 100%);
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  border: 2px solid #fde68a;
}
[data-theme="light"] .team-podium-entry {
  background: rgba(0,0,0,0.03);
}
[data-theme="light"] .podium-count {
  color: #475569;
}
.podium-medal {
  font-size: 2.5rem;
  animation: medal-bounce 0.8s infinite alternate;
}
@keyframes medal-bounce {
  0% { transform: translateY(0) scale(1); }
  100% { transform: translateY(-8px) scale(1.1); }
}
.podium-name {
  font-size: 1.1rem;
  font-weight: bold;
}
.podium-km {
  color: #dfe6e9;
  font-size: 0.95rem;
}
.podium-clap {
  animation: clap-wave 0.6s infinite alternate;
}
@keyframes clap-wave {
  0% { transform: scale(1); }
  100% { transform: scale(1.2); }
}
.standing-ovation {
  margin-top: 1rem;
  font-size: 1.5rem;
  letter-spacing: 0.5rem;
  animation: ovation-pulse 1s infinite alternate;
}
@keyframes ovation-pulse {
  0% { opacity: 0.5; transform: scale(0.95); }
  100% { opacity: 1; transform: scale(1.05); }
}
/* Achievement toast notifications */
.fun-toast {
  position: fixed;
  right: -400px;
  padding: 1rem 1.5rem;
  background: linear-gradient(135deg, #2d3436, #636e72);
  color: white;
  border-radius: 12px;
  border-left: 5px solid #feca57;
  box-shadow: 0 8px 25px rgba(0,0,0,0.4);
  z-index: 9999;
  font-weight: bold;
  font-size: 0.95rem;
  max-width: 350px;
  transition: right 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}
.fun-toast.show {
  right: 20px;
}
/* Progress bar toward next badge */
.progress-bar-container {
  background: #e0e0e0;
  border-radius: 8px;
  height: 8px;
  margin-top: 4px;
  overflow: hidden;
}
[data-theme="dark"] .progress-bar-container {
  background: #374151;
}
.progress-bar {
  background: linear-gradient(90deg, #4CAF50, #8BC34A);
  height: 100%;
  border-radius: 8px;
  transition: width 0.3s;
}
.progress-label {
  font-size: 0.7rem;
  color: #6b7280;
  display: block;
  margin-top: 2px;
}
[data-theme="dark"] .progress-label {
  color: #9ca3af;
}
/* Awards section */
.awards-section {
  max-width: 900px;
  margin: 1.5rem auto;
  padding: 1.5rem;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border-radius: 16px;
  border: 2px solid #ffd700;
  box-shadow: 0 4px 20px rgba(255, 215, 0, 0.2);
}
[data-theme="light"] .awards-section {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}
.awards-title {
  text-align: center;
  font-size: 1.4rem;
  font-weight: bold;
  color: #ffd700;
  margin-bottom: 1rem;
}
[data-theme="light"] .awards-title {
  color: #b45309;
}
.awards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
}
.award-card {
  background: linear-gradient(135deg, rgba(255,215,0,0.1), rgba(255,215,0,0.05));
  border: 1px solid rgba(255,215,0,0.3);
  border-radius: 12px;
  padding: 1rem;
  text-align: center;
  transition: transform 0.2s;
}
.award-card:hover {
  transform: translateY(-4px);
}
[data-theme="light"] .award-card {
  background: linear-gradient(135deg, rgba(255,215,0,0.15), rgba(255,215,0,0.05));
  border-color: #fbbf24;
}
.award-emoji {
  font-size: 2em;
  margin-bottom: 0.3rem;
}
.award-title {
  font-weight: bold;
  font-size: 0.85rem;
  color: #fbbf24;
  margin-bottom: 0.3rem;
}
[data-theme="light"] .award-title {
  color: #b45309;
}
.award-winner {
  font-weight: bold;
  font-size: 1rem;
  color: #fff;
  margin-bottom: 0.2rem;
}
[data-theme="light"] .award-winner {
  color: #1e293b;
}
.award-value {
  font-size: 0.85rem;
  color: #a0aec0;
}
[data-theme="light"] .award-value {
  color: #64748b;
}
.award-detail {
  font-size: 0.75rem;
  color: #718096;
  margin-top: 0.2rem;
}
/* Battles section */
.battles-section {
  max-width: 900px;
  margin: 1.5rem auto;
  padding: 1.5rem;
  background: linear-gradient(135deg, #1a1a2e 0%, #2d1b3d 100%);
  border-radius: 16px;
  border: 2px solid #e74c3c;
  box-shadow: 0 4px 20px rgba(231, 76, 60, 0.2);
}
[data-theme="light"] .battles-section {
  background: linear-gradient(135deg, #fff5f5 0%, #ffe0e0 100%);
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  border-color: #f87171;
}
.battles-title {
  text-align: center;
  font-size: 1.4rem;
  font-weight: bold;
  color: #e74c3c;
  margin-bottom: 1rem;
}
[data-theme="light"] .battles-title {
  color: #dc2626;
}
.battles-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.battle-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.8rem;
  background: linear-gradient(135deg, rgba(231,76,60,0.1), rgba(243,156,18,0.1));
  border: 1px solid rgba(231,76,60,0.3);
  border-radius: 12px;
  padding: 1rem;
  text-align: center;
}
[data-theme="light"] .battle-card {
  background: linear-gradient(135deg, rgba(248,113,113,0.1), rgba(251,191,36,0.1));
  border-color: #fca5a5;
}
.battle-team {
  font-weight: bold;
  font-size: 1rem;
  color: #fff;
}
[data-theme="light"] .battle-team {
  color: #1e293b;
}
.battle-vs {
  font-size: 1.2rem;
  font-weight: bold;
  color: #f39c12;
  animation: battle-pulse 1s infinite alternate;
}
@keyframes battle-pulse {
  0% { transform: scale(1); opacity: 0.8; }
  100% { transform: scale(1.2); opacity: 1; }
}
.battle-ecart {
  width: 100%;
  font-weight: bold;
  font-size: 0.9rem;
  color: #e74c3c;
  margin-top: 0.3rem;
}
[data-theme="light"] .battle-ecart {
  color: #dc2626;
}
</style>
"""

    confetti_script = ""
    if is_fun:
        confetti_script = """
<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
<script>
  window.addEventListener('load', function() {
    // Confetti on load
    var duration = 3 * 1000;
    var animationEnd = Date.now() + duration;
    var defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 0 };
    function randomInRange(min, max) { return Math.random() * (max - min) + min; }
    var interval = setInterval(function() {
      var timeLeft = animationEnd - Date.now();
      if (timeLeft <= 0) return clearInterval(interval);
      var particleCount = 50 * (timeLeft / duration);
      confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 } }));
      confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 } }));
    }, 250);

    // Rotating motivational quotes
    var quotes = [
      "La sueur, c'est juste tes bourrelets qui pleurent \\ud83d\\ude2d",
      "Cours comme si le dernier pain au chocolat t'attendait \\ud83e\\udd50",
      "Tes fesses te remercieront... un jour \\ud83c\\udf51",
      "On n'est pas l\\u00e0 pour souffrir... ah si en fait \\ud83d\\ude05",
      "Chaque kilom\\u00e8tre te rapproche de Mars ! \\ud83d\\ude80",
      "Le canap\\u00e9 est ton ennemi. Le bitume est ton ami. \\ud83d\\udeb6",
      "T'as pas fait tout \\u00e7a pour abandonner maintenant ! \\ud83d\\udcaa",
      "M\\u00eame un escargot finit par arriver \\ud83d\\udc0c",
      "Ton corps te d\\u00e9teste l\\u00e0, mais il t'aimera demain \\u2764\\ufe0f",
      "Si t'arrives \\u00e0 lire \\u00e7a en courant, ralentis pas ! \\ud83c\\udfc3",
      "Cours plus vite que ta digestion \\ud83d\\udca9"
    ];
    var quoteEl = document.getElementById('fun-quote-text');
    if (quoteEl) {
      var qi = 0;
      quoteEl.textContent = quotes[0];
      setInterval(function() {
        quoteEl.style.opacity = '0';
        setTimeout(function() {
          qi = (qi + 1) % quotes.length;
          quoteEl.textContent = quotes[qi];
          quoteEl.style.opacity = '1';
        }, 500);
      }, 4000);
    }

    // Achievement toast notifications
    var allToasts = [
      "\\ud83c\\udfc6 Achievement: Tu as ouvert la page ! +10 points motivation",
      "\\ud83c\\udfc6 Achievement: Stalker de classement d\\u00e9tect\\u00e9 !",
      "\\ud83c\\udfc6 Achievement: Mode Fun activ\\u00e9 ! Tu g\\u00e8res !",
      "\\ud83d\\udc40 Achievement: Espionnage de concurrents en cours...",
      "\\ud83e\\uddb6 Achievement: Tes mollets ont senti ta pr\\u00e9sence",
      "\\ud83c\\udf55 Achievement: Calories brul\\u00e9es = 1 pizza gratuite",
      "\\ud83d\\udca9 Achievement: Tu scrolles au lieu de courir !",
      "\\ud83e\\udd21 Achievement: Fan n\\u00b01 du Mode Fun",
      "\\ud83d\\ude34 Achievement: Le canap\\u00e9 pleure ton absence",
      "\\ud83e\\uddd0 Achievement: Analyse tactique du classement"
    ];
    // Pick 3 random toasts
    var toasts = [];
    var indices = [];
    while (toasts.length < 3 && indices.length < allToasts.length) {
      var ri = Math.floor(Math.random() * allToasts.length);
      if (indices.indexOf(ri) === -1) { indices.push(ri); toasts.push(allToasts[ri]); }
    }
    function showToast(msg, delay, topOffset) {
      setTimeout(function() {
        var t = document.createElement('div');
        t.className = 'fun-toast';
        t.textContent = msg;
        t.style.top = topOffset + 'px';
        document.body.appendChild(t);
        setTimeout(function() { t.classList.add('show'); }, 50);
        setTimeout(function() {
          t.classList.remove('show');
          setTimeout(function() { t.remove(); }, 600);
        }, 4000);
      }, delay);
    }
    showToast(toasts[0], 3500, 20);
    showToast(toasts[1], 5500, 90);
    showToast(toasts[2], 7500, 160);

    // Team podium carousel rotation
    var teamEntries = document.querySelectorAll('.team-podium-entry');
    if (teamEntries.length > 3) {
      var teamOffset = 0;
      setInterval(function() {
        teamOffset = (teamOffset + 1) % teamEntries.length;
        teamEntries.forEach(function(el, i) {
          var pos = (i - teamOffset + teamEntries.length) % teamEntries.length;
          if (pos < 3) {
            el.style.display = 'flex';
            el.style.opacity = '0';
            setTimeout(function() { el.style.opacity = '1'; }, 50);
          } else {
            el.style.opacity = '0';
            setTimeout(function() { el.style.display = 'none'; }, 500);
          }
        });
      }, 3000);
    }

    // Konami code Easter egg
    var konamiSeq = [38,38,40,40,37,39,37,39,66,65];
    var konamiPos = 0;
    document.addEventListener('keydown', function(e) {
      if (e.keyCode === konamiSeq[konamiPos]) {
        konamiPos++;
        if (konamiPos === konamiSeq.length) {
          konamiPos = 0;
          // Mega confetti burst
          var end = Date.now() + 5000;
          var iv = setInterval(function() {
            if (Date.now() > end) return clearInterval(iv);
            confetti({ particleCount: 100, spread: 160, origin: { x: Math.random(), y: Math.random() * 0.6 } });
          }, 100);
          // Fun alert
          setTimeout(function() {
            alert("\\ud83c\\udf89 KONAMI CODE ACTIV\\u00c9 ! \\ud83c\\udf89\\n\\nTu es officiellement un NINJA du classement !\\nBonus : +1000 km imaginaires \\ud83e\\uddb8");
          }, 500);
        }
      } else {
        konamiPos = e.keyCode === konamiSeq[0] ? 1 : 0;
      }
    });
  });
</script>
"""

    html_content = f"""<!DOCTYPE html>
<html lang="fr" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
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

[data-theme="dark"] {{
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
  padding: 2rem 1.5rem 1.5rem;
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
.hero-subtitle {{
  color: rgba(255,255,255,0.7);
  font-size: 1rem;
  font-weight: 400;
  position: relative;
  font-family: var(--font-body);
}}
.depistage-msg {{
  color: #fbbf24;
  font-family: var(--font-heading);
  font-size: 1.3rem;
  font-weight: 700;
  margin-top: 0.7rem;
  text-shadow: 0 1px 4px rgba(0,0,0,0.3);
  position: relative;
}}


/* ── Stats cards ── */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
  margin: -1.5rem auto 0.5rem;
  max-width: 900px;
  padding: 0 1.5rem;
  position: relative;
  z-index: 2;
}}
.stat-card {{
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 0.8rem;
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
  padding: 1rem 1.5rem;
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
[data-theme="dark"] .results-table tbody tr:nth-child(even) {{
  background: rgba(255,255,255,0.02);
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
  margin-top: 1.5rem;
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
.footer-refresh {{
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  font-size: 0.85rem;
  color: var(--footer-text);
}}
.footer-refresh-icon {{
  display: inline-block;
  margin-right: 0.4rem;
  animation: syncPulse 2s ease-in-out infinite;
  color: var(--accent);
}}
@keyframes syncPulse {{
  0%, 100% {{ opacity: 0.7; transform: scale(1); }}
  50% {{ opacity: 1; transform: scale(1.1); }}
}}
.footer-refresh-text {{
  display: block;
  font-weight: 500;
  margin-bottom: 0.25rem;
}}
.footer-refresh-timestamp {{
  display: block;
  font-size: 0.75rem;
  opacity: 0.8;
  margin-top: 0.25rem;
}}
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

/* ── FAB menu ── */
.fab-menu {{
  position: fixed;
  top: 1.5rem;
  right: 1.5rem;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
}}
.fab-btn {{
  background: linear-gradient(135deg, var(--accent), var(--accent-dark, var(--accent)));
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
}}
.fab-btn:hover {{ transform: scale(1.1); box-shadow: var(--shadow-lg); }}
.fab-dropdown {{
  display: none;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  min-width: 140px;
}}
.fab-dropdown.open {{ display: flex; }}
.fab-item {{
  background: none;
  border: none;
  color: var(--text);
  padding: 0.65rem 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.9rem;
  transition: background 0.15s;
  white-space: nowrap;
  text-align: left;
  width: 100%;
}}
.fab-item:hover {{ background: var(--bg-hover, rgba(0,0,0,0.06)); }}
.fab-item i {{ width: 1.2rem; text-align: center; color: var(--accent); }}
/* ── Video modal ── */
.video-modal {{
  display: none;
  position: fixed;
  inset: 0;
  z-index: 2000;
  align-items: center;
  justify-content: center;
}}
.video-modal.open {{ display: flex; }}
.video-modal-backdrop {{ position: absolute; inset: 0; background: rgba(0,0,0,0.75); }}
.video-modal-content {{
  position: relative;
  z-index: 1;
  width: min(360px, 92vw);
  aspect-ratio: 9 / 16;
  background: #000;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(0,0,0,0.5);
}}
.video-modal-close {{
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 2;
  background: rgba(0,0,0,0.5);
  border: none;
  color: white;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  font-size: 1.2rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}}
.modal-video {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
/* About Modal */
.about-modal {{ display: none; position: fixed; inset: 0; z-index: 2000; align-items: center; justify-content: center; padding: 1rem; }}
.about-modal.open {{ display: flex; }}
.about-modal-backdrop {{ position: absolute; inset: 0; background: rgba(0,0,0,0.7); }}
.about-modal-content {{ position: relative; background: var(--bg-card, #fff); border-radius: 1rem; padding: 2rem; max-width: 520px; width: 100%; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.3); color: var(--text, #363636); }}
.about-modal-content strong {{ color: var(--text, #363636); }}
.about-modal-close {{ position: absolute; top: 1rem; right: 1rem; background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text, #363636); line-height: 1; }}
.about-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 2px solid #3273dc22; }}
.about-emoji {{ font-size: 2rem; }}
.about-header h2 {{ font-size: 1.25rem; font-weight: 700; color: #3273dc; margin: 0; }}
.about-section {{ margin-bottom: 1.25rem; padding-bottom: 1.25rem; border-bottom: 1px solid rgba(128,128,128,0.15); }}
.about-section:last-of-type {{ border-bottom: none; }}
.about-section h3 {{ font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #3273dc; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }}
.about-section p {{ font-size: 0.92rem; line-height: 1.6; margin: 0; }}
.about-footer {{ margin-top: 1.5rem; text-align: center; }}
.about-link {{ display: inline-flex; align-items: center; gap: 0.5rem; background: #3273dc; color: #fff; padding: 0.6rem 1.2rem; border-radius: 2rem; text-decoration: none; font-size: 0.88rem; font-weight: 600; transition: background 0.2s; }}
.about-link:hover {{ background: #2366d1; color: #fff; }}

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


</style>
{fun_css}
</head>
<body>

<div class="fab-menu" id="fab-menu">
  <button class="fab-btn" id="fab-toggle" aria-expanded="false" title="Menu">
    <i class="fas fa-bars"></i>
  </button>
  <div class="fab-dropdown" id="fab-dropdown">
    <button class="fab-item" id="theme-toggle">
      <i class="fas fa-moon"></i><span>Thème</span>
    </button>
    <button class="fab-item" id="help-btn">
      <i class="fas fa-question-circle"></i><span>Aide</span>
    </button>
    <button class="fab-item" id="about-btn" aria-label="À propos">
      <i class="fas fa-circle-info"></i>
      <span>À propos</span>
    </button>
  </div>
</div>

<div class="video-modal" id="video-modal">
  <div class="video-modal-backdrop" id="video-modal-backdrop"></div>
  <div class="video-modal-content">
    <button class="video-modal-close" id="video-modal-close">&times;</button>
    <video controls preload="none" class="modal-video" id="modal-video">
      <source src="{SUBSCRIBE_VIDEO_URL}" type="video/mp4">
    </video>
  </div>
</div>

<div class="about-modal" id="about-modal">
  <div class="about-modal-backdrop" id="about-modal-backdrop"></div>
  <div class="about-modal-content">
    <button class="about-modal-close" id="about-modal-close">&times;</button>
    <div class="about-header">
      <span class="about-emoji">🩵</span>
      <h2>À propos du Défi Mars Bleu</h2>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-person-running"></i> Le Défi</h3>
      <p>Durant tout le mois de mars, des milliers de courageux chaussent leurs baskets —
        ou enfilent leurs chaussons — pour accumuler des kilomètres ensemble.
        Marche, course, vélo, natation : tout compte !<br><br>
        L'objectif ? Bouger, se connecter, et prouver qu'on peut sauver des vies
        en sueur et en bonne humeur. Parce que rester assis sur son canapé n'a
        jamais guéri personne (médicalement parlant).</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-ribbon"></i> Le Cancer Colorectal : Les Chiffres qui Piquent</h3>
      <p>2ème cancer le plus fréquent en France. 1 personne sur 17 sera concernée
        un jour dans sa vie. Chaque année, plus de 43 000 nouveaux cas diagnostiqués.<br><br>
        La bonne nouvelle ? Dépisté tôt, il se guérit dans <strong>9 cas sur 10</strong>.
        Oui, vous avez bien lu. Neuf sur dix. Votre côlon mérite qu'on s'y intéresse.</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-circle-check"></i> Pourquoi Se Dépister ?</h3>
      <p>À partir de 50 ans (et jusqu'à 74 ans), le test de dépistage est
        <strong>gratuit, discret et réalisable chez soi</strong>. Pas d'excuse !<br><br>
        Demandez votre kit à votre médecin traitant et rejoignez le camp
        des gens qui prennent soin d'eux. Votre famille vous en remerciera.
        Votre côlon aussi, même s'il est pudique.</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-rotate"></i> Comment ça marche ?</h3>
      <p>Ce site est généré automatiquement depuis les données <strong>ZapSport</strong>
        et se rafraîchit toutes les <strong>10 minutes</strong>.<br><br>
        Pour que vos kilomètres apparaissent ici, pensez à
        <strong>télécharger vos parcours sur ZapSport</strong> — sans ça, on ne peut
        pas les comptabiliser. Votre GPS mérite d'être entendu !</p>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-user-plus"></i> S'inscrire au Défi</h3>
      <p>Pas encore inscrit ? Les inscriptions se font directement en ligne —
        rejoignez les équipes et commencez à accumuler des kilomètres pour la bonne cause !</p>
      <div style="margin-top:0.75rem; text-align:center;">
        <a href="https://www.sport-up.fr/www/inscription_en_ligne_2.0/inscription-39684-ORG-JAVGH.htm"
           target="_blank" rel="noopener" class="about-link" style="font-size:0.82rem;">
          <i class="fas fa-arrow-up-right-from-square"></i>
          S'inscrire sur sport-up.fr
        </a>
      </div>
    </div>
    <div class="about-section">
      <h3><i class="fas fa-heart"></i> Réalisé par</h3>
      <p>Ce site a été concocté par
        <a href="https://www.instagram.com/samchmou/" target="_blank" rel="noopener">@samchmou</a> des
        <a href="https://www.instagram.com/nicerunners06/" target="_blank" rel="noopener">@nicerunners</a>
        pour aider à la motivation des équipes —
        parce qu'un tableau de bord bien visible, ça donne des ailes
        (ou au moins des jambes).</p>
    </div>
    <div class="about-footer">
      <a href="https://www.marsbleuconnecte.fr/#top" target="_blank" rel="noopener" class="about-link">
        <i class="fas fa-arrow-up-right-from-square"></i>
        En savoir plus sur marsbleuconnecte.fr
      </a>
    </div>
  </div>
</div>

<div class="hero-section">
  <a href="https://www.marsbleuconnecte.fr/#top" target="_blank" title="Aller au site Mars Bleu Connecté">
    <img src="{logo_url}" alt="Mars Bleu" class="hero-logo">
  </a>
  <h1 class="hero-title">{hero_title_html}</h1>
  <div class="hero-divider"></div>
  <p class="hero-subtitle">{hero_subtitle}</p>
  <p class="depistage-msg">À partir de 50 ans, je me fais dépister !</p>
  {switch_link}
</div>

<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-icon"><i class="fas fa-users"></i></div>
    <div>
      <div class="stat-value">{total_participants}</div>
      <div class="stat-label">{total_participants_label}</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon"><i class="fas fa-road"></i></div>
    <div>
      <div class="stat-value">{total_km:,.1f}</div>
      <div class="stat-label">{total_km_label}</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon"><i class="fas fa-people-group"></i></div>
    <div>
      <div class="stat-value">{nb_equipes}</div>
      <div class="stat-label">{nb_equipes_label}</div>
    </div>
  </div>
</div>

<div class="main-content">
  {fun_stats}
  {awards_html}
  {battles_html}

  <div class="search-wrapper">
    <div class="control has-icons-left">
      <input class="input" type="text" id="search" placeholder="Rechercher un participant(e) ou une équipe...">
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
    {team_podium_html}
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
  </p>
  <p style="margin-top:0.5rem">
    <i class="fas fa-ribbon" style="color: var(--gold);"></i>
    <span style="font-family: var(--font-heading); font-weight: 700;">Mars Bleu</span> &mdash; Sensibilisation au cancer colorectal
  </p>
  <div class="footer-refresh">
    <span class="footer-refresh-text">
      <i class="fas fa-sync footer-refresh-icon"></i>
      Données mises à jour automatiquement toutes les 10 minutes
    </span>
    <span class="footer-refresh-timestamp">
      Dernière mise à jour : {now}
    </span>
  </div>
  <p class="footer-vibed">
    <span class="rainbow">Vibed with love</span> by <a href="https://www.instagram.com/samchmou/" target="_blank">SamChmou</a>
    &mdash;
    🏃 <a href="https://www.instagram.com/nicerunners06/" target="_blank">Nice Runners</a>
    &middot;
    🚴 <a href="https://www.instagram.com/nicecyclists/" target="_blank">Nice Cyclists</a>
    &middot;
    🏊 <a href="https://www.instagram.com/niceswimmers/" target="_blank">Nice Swimmers</a>
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

// FAB menu
(function() {{
  var html = document.documentElement;
  var fabToggle = document.getElementById('fab-toggle');
  var fabDropdown = document.getElementById('fab-dropdown');
  var themeToggle = document.getElementById('theme-toggle');
  var helpBtn = document.getElementById('help-btn');
  var videoModal = document.getElementById('video-modal');
  var videoModalClose = document.getElementById('video-modal-close');
  var videoModalBackdrop = document.getElementById('video-modal-backdrop');
  var modalVideo = document.getElementById('modal-video');
  var aboutBtn = document.getElementById('about-btn');
  var aboutModal = document.getElementById('about-modal');
  var aboutModalClose = document.getElementById('about-modal-close');
  var aboutModalBackdrop = document.getElementById('about-modal-backdrop');

  // Theme init
  var saved = localStorage.getItem('theme');
  var theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  html.setAttribute('data-theme', theme);
  updateThemeIcon(theme);

  function updateThemeIcon(t) {{
    var icon = themeToggle.querySelector('i');
    icon.className = t === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
  }}

  // FAB open/close
  fabToggle.addEventListener('click', function(e) {{
    e.stopPropagation();
    var open = fabDropdown.classList.toggle('open');
    fabToggle.setAttribute('aria-expanded', open);
  }});
  document.addEventListener('click', function() {{
    fabDropdown.classList.remove('open');
    fabToggle.setAttribute('aria-expanded', false);
  }});

  // Theme toggle
  themeToggle.addEventListener('click', function() {{
    var cur = html.getAttribute('data-theme');
    var nxt = cur === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', nxt);
    localStorage.setItem('theme', nxt);
    updateThemeIcon(nxt);
    fabDropdown.classList.remove('open');
  }});

  // Help → open video modal
  helpBtn.addEventListener('click', function() {{
    videoModal.classList.add('open');
    fabDropdown.classList.remove('open');
  }});

  // About modal
  aboutBtn.addEventListener('click', function() {{
    aboutModal.classList.add('open');
    fabDropdown.classList.remove('open');
    fabToggle.setAttribute('aria-expanded', 'false');
  }});
  [aboutModalClose, aboutModalBackdrop].forEach(function(el) {{
    el.addEventListener('click', function() {{ aboutModal.classList.remove('open'); }});
  }});

  function closeModal() {{
    videoModal.classList.remove('open');
    modalVideo.pause();
  }}
  videoModalClose.addEventListener('click', closeModal);
  videoModalBackdrop.addEventListener('click', closeModal);
}})();
</script>
{confetti_script}
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

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Scraping des résultats Mars Bleu...")
    participants = scrape_all()
    print(f"\nTotal : {len(participants)} participants")

    print("Génération du HTML classique...")
    html_content = generate_html(participants, is_fun=False)
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    print("index.html généré avec succès.")

    print("Génération du HTML délire...")
    fun_html_content = generate_html(participants, is_fun=True)
    with open(os.path.join(OUTPUT_DIR, "fun.html"), "w", encoding="utf-8") as f:
        f.write(fun_html_content)
    print("fun.html généré avec succès.")

    # Générer les pages individuelles pour les 10 premières équipes
    participants_sorted = sorted(participants, key=km_float, reverse=True)
    teams, equipe_members = build_teams(participants_sorted)
    print(f"\nGénération des pages équipes (top {min(10, len(teams))})...")
    for idx, team in enumerate(teams[:10], 1):
        slug = slugify(team["equipe"])
        members = equipe_members[team["equipe"].lower()]
        for is_fun in [False, True]:
            suffix = "-fun" if is_fun else ""
            filename = os.path.join(OUTPUT_DIR, f"equipe-{slug}{suffix}.html")
            team_html = generate_team_page(team, idx, members, is_fun)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(team_html)
            print(f"  {filename} généré.")
    print("Pages équipes générées avec succès.")


if __name__ == "__main__":
    main()
