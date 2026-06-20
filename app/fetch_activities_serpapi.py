#!/usr/bin/env python3
"""
SerpAPI Activity Fetcher — ZenifyTrip Fixture Enricher
======================================================
Recherche les activités touristiques réelles pour chaque ville tunisienne
via Google Maps (SerpAPI) et enrichit les fichiers JSON fixtures.

Usage:
    python -m app.fetch_activities_serpapi --key <SERPAPI_KEY> --city all
    python -m app.fetch_activities_serpapi --key <SERPAPI_KEY> --city sousse
    python -m app.fetch_activities_serpapi --key <SERPAPI_KEY> --city sousse djerba tunis

    # Ou via variable d'environnement :
    set SERPAPI_KEY=votre_cle
    python -m app.fetch_activities_serpapi --city all
"""

import argparse
import json
import os
import re
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
SERPAPI_URL      = "https://serpapi.com/search"
FIXTURES_DIR     = Path(__file__).parent / "data" / "fixtures" / "raw"
PROGRESS_FILE    = Path(__file__).parent / "data" / "fixtures" / "fetch_progress.json"
REQUESTS_DELAY   = 1.5   # secondes entre chaque requête (rate limit SerpAPI)
MAX_NEW_PER_CITY = 30    # max nouvelles activités par requête
MIN_RATING       = 3.0   # ignorer les lieux avec rating < 3.0

# ──────────────────────────────────────────────────────────────────────────────
# TOUTES LES VILLES (39 destinations tunisiennes)
# ──────────────────────────────────────────────────────────────────────────────
CITIES = {
    # ── TIER 1 ─────────────────────────────────────────────────────────────────
    "djerba":           {"city_en": "Djerba",           "city_fr": "Djerba",           "tier": 1},
    "sousse":           {"city_en": "Sousse",           "city_fr": "Sousse",           "tier": 1},
    "tunis":            {"city_en": "Tunis",            "city_fr": "Tunis",            "tier": 1},
    "hammamet":         {"city_en": "Hammamet",         "city_fr": "Hammamet",         "tier": 1},
    "tozeur":           {"city_en": "Tozeur",           "city_fr": "Tozeur",           "tier": 1},
    "kairouan":         {"city_en": "Kairouan",         "city_fr": "Kairouan",         "tier": 1},
    "tabarka":          {"city_en": "Tabarka",          "city_fr": "Tabarka",          "tier": 1},
    "monastir":         {"city_en": "Monastir",         "city_fr": "Monastir",         "tier": 1},
    "mahdia":           {"city_en": "Mahdia",           "city_fr": "Mahdia",           "tier": 1},
    "sfax":             {"city_en": "Sfax",             "city_fr": "Sfax",             "tier": 1},
    "bizerte":          {"city_en": "Bizerte",          "city_fr": "Bizerte",          "tier": 1},
    "nabeul":           {"city_en": "Nabeul",           "city_fr": "Nabeul",           "tier": 1},
    # ── TIER 2 ─────────────────────────────────────────────────────────────────
    "sidi_bou_said":    {"city_en": "Sidi Bou Said",    "city_fr": "Sidi Bou Saïd",   "tier": 2},
    "douz":             {"city_en": "Douz",             "city_fr": "Douz",             "tier": 2},
    "matmata":          {"city_en": "Matmata",          "city_fr": "Matmata",          "tier": 2},
    "tataouine":        {"city_en": "Tataouine",        "city_fr": "Tataouine",        "tier": 2},
    "la_marsa":         {"city_en": "La Marsa",         "city_fr": "La Marsa",         "tier": 2},
    "nefta":            {"city_en": "Nefta",            "city_fr": "Nefta",            "tier": 2},
    "ain_draham":       {"city_en": "Ain Draham",       "city_fr": "Ain Draham",       "tier": 2},
    "gafsa":            {"city_en": "Gafsa",            "city_fr": "Gafsa",            "tier": 2},
    "sbeitla":          {"city_en": "Sbeitla",          "city_fr": "Sbeitla",          "tier": 2},
    "kelibia":          {"city_en": "Kelibia",          "city_fr": "Kélibia",          "tier": 2},
    "gabes":            {"city_en": "Gabes",            "city_fr": "Gabès",            "tier": 2},
    "zarzis":           {"city_en": "Zarzis",           "city_fr": "Zarzis",           "tier": 2},
    "carthage":         {"city_en": "Carthage",         "city_fr": "Carthage",         "tier": 2},
    "el_haouaria":      {"city_en": "El Haouaria",      "city_fr": "El Haouaria",      "tier": 2},
    "korba":            {"city_en": "Korba",            "city_fr": "Korba",            "tier": 2},
    "kebili":           {"city_en": "Kebili",           "city_fr": "Kébili",           "tier": 2},
    "le_kef":           {"city_en": "Le Kef",           "city_fr": "Le Kef",           "tier": 2},
    "dougga":           {"city_en": "Dougga",           "city_fr": "Dougga",           "tier": 2},
    "la_goulette":      {"city_en": "La Goulette",      "city_fr": "La Goulette",      "tier": 2},
    # ── TIER 3 ─────────────────────────────────────────────────────────────────
    "medenine":         {"city_en": "Medenine",         "city_fr": "Médenine",         "tier": 3},
    "sidi_bouzid":      {"city_en": "Sidi Bouzid",      "city_fr": "Sidi Bouzid",      "tier": 3},
    "jendouba":         {"city_en": "Jendouba",         "city_fr": "Jendouba",         "tier": 3},
    "ariana":           {"city_en": "Ariana",           "city_fr": "Ariana",           "tier": 3},
    "kasserine":        {"city_en": "Kasserine",        "city_fr": "Kasserine",        "tier": 3},
    "ben_arous":        {"city_en": "Ben Arous",        "city_fr": "Ben Arous",        "tier": 3},
    "siliana":          {"city_en": "Siliana",          "city_fr": "Siliana",          "tier": 3},
    "menzel_bourguiba": {"city_en": "Menzel Bourguiba", "city_fr": "Menzel Bourguiba", "tier": 3},
}

# ──────────────────────────────────────────────────────────────────────────────
# MAPPING : Types Google Maps → activity_type Pydantic
# ──────────────────────────────────────────────────────────────────────────────
# Les types sont ceux retournés par SerpAPI dans le champ "type"
ACTIVITY_TYPE_MAP = {
    # → culture
    "tourist attraction": "culture",
    "museum":             "culture",
    "art gallery":        "culture",
    "art museum":         "culture",
    "historical landmark":"culture",
    "historic site":      "culture",
    "ruins":              "culture",
    "archaeological site":"culture",
    "monument":           "culture",
    "cultural center":    "culture",
    "theater":            "culture",
    "mosque":             "culture",
    "church":             "culture",
    "synagogue":          "culture",
    "religious site":     "culture",
    "castle":             "culture",
    "fortress":           "culture",
    "palace":             "culture",
    # → nature
    "national park":      "nature",
    "nature reserve":     "nature",
    "natural feature":    "nature",
    "park":               "nature",
    "garden":             "nature",
    "botanical garden":   "nature",
    "wildlife park":      "nature",
    "zoo":                "nature",
    "aquarium":           "nature",
    "island":             "nature",
    "lake":               "nature",
    "forest":             "nature",
    # → relax
    "beach":              "relax",
    "spa":                "relax",
    "wellness center":    "relax",
    "golf course":        "relax",
    "resort":             "relax",
    "hammam":             "relax",
    # → adventure
    "amusement park":     "adventure",
    "water park":         "adventure",
    "sports complex":     "adventure",
    "diving":             "adventure",
    "atv":                "adventure",
    "quad":               "adventure",
    "equestrian":         "adventure",
    "water sport":        "adventure",
    "hiking":             "adventure",
    "camping":            "adventure",
    # → city_experience (default pour le reste)
    "restaurant":         "city_experience",
    "cafe":               "city_experience",
    "bar":                "city_experience",
    "night club":         "city_experience",
    "nightclub":          "city_experience",
    "shopping mall":      "city_experience",
    "market":             "city_experience",
    "souvenir shop":      "city_experience",
    "food court":         "city_experience",
    "street food":        "city_experience",
}

# Types à exclure (pas d'intérêt touristique)
EXCLUDED_TYPES = {
    "hospital", "clinic", "pharmacy", "gas station", "bank",
    "atm", "car rental", "real estate", "lawyer", "accounting",
    "insurance", "school", "university", "government office",
    "police", "fire station", "post office", "car dealer",
    "parking", "lodging", "hotel",  # hôtels = pas des activités
}

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Normalise un nom pour la déduplication (minuscules, sans accents, sans espaces)."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def is_duplicate(name: str, existing_names: set) -> bool:
    """Vérifie si un nom est déjà présent (matching exact ou proche)."""
    n = normalize(name)
    for existing in existing_names:
        e = normalize(existing)
        # Exact match
        if n == e:
            return True
        # Substring match (l'un contient l'autre avec 80%+ de caractères)
        shorter, longer = (n, e) if len(n) <= len(e) else (e, n)
        if len(shorter) >= 5 and shorter in longer:
            return True
    return False


def map_activity_type(google_type: str) -> str:
    """Convertit un type Google Maps en activity_type Pydantic."""
    if not google_type:
        return "city_experience"
    t = google_type.lower().strip()
    # Check direct match
    if t in ACTIVITY_TYPE_MAP:
        return ACTIVITY_TYPE_MAP[t]
    # Check partial match
    for key, val in ACTIVITY_TYPE_MAP.items():
        if key in t or t in key:
            return val
    return "city_experience"  # default


def is_excluded(google_type: str) -> bool:
    """Retourne True si le type doit être ignoré."""
    if not google_type:
        return False
    t = google_type.lower().strip()
    return any(excl in t for excl in EXCLUDED_TYPES)


def load_fixture(city_slug: str) -> dict:
    """Charge le fichier JSON fixture d'une ville."""
    path = FIXTURES_DIR / f"{city_slug}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fichier fixture introuvable: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_fixture(city_slug: str, data: dict) -> None:
    """Sauvegarde le fichier JSON fixture d'une ville."""
    path = FIXTURES_DIR / f"{city_slug}.json"
    data["total"] = len(data["activities"])
    data["fetched_at"] = str(date.today())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ Sauvegardé: {path.name} ({data['total']} activités)")


def get_next_id(city_slug: str, existing_activities: list) -> int:
    """Retourne le prochain ID disponible pour une ville."""
    if not existing_activities:
        return 1
    ids = []
    prefix = f"{city_slug}_"
    for act in existing_activities:
        aid = act.get("id", "")
        if aid.startswith(prefix):
            try:
                ids.append(int(aid[len(prefix):]))
            except ValueError:
                pass
    return max(ids) + 1 if ids else len(existing_activities) + 1


# ──────────────────────────────────────────────────────────────────────────────
# SERPAPI REQUESTS
# ──────────────────────────────────────────────────────────────────────────────

def search_google_maps(city_en: str, query: str, api_key: str) -> list:
    """
    Recherche des activités via SerpAPI Google Maps.
    Retourne une liste de résultats locaux bruts.
    """
    params = {
        "engine":   "google_maps",
        "q":        f"{query} {city_en} Tunisia",
        "type":     "search",
        "hl":       "fr",
        "gl":       "tn",
        "api_key":  api_key,
    }
    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("local_results", [])
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Erreur SerpAPI ({query}): {e}")
        return []


def fetch_all_queries(city_en: str, api_key: str) -> list:
    """
    Lance plusieurs requêtes pour couvrir les différents types d'activités.
    Retourne une liste combinée de résultats bruts (avec duplicates possibles).
    """
    queries = [
        "things to do tourist attractions",
        "quad ATV sortie aventure",
        "nightclub bar soirée",
        "shopping mall centre commercial",
        "balade nature randonnée",
        "plage activités nautiques",
        "restaurant gastronomique cuisine locale",
        "hammam spa bien-être",
    ]

    all_results = []
    for q in queries:
        print(f"    🔍 Requête: '{q} {city_en} Tunisia'")
        results = search_google_maps(city_en, q, api_key)
        all_results.extend(results)
        time.sleep(REQUESTS_DELAY)

    return all_results


# ──────────────────────────────────────────────────────────────────────────────
# PARSING ET CONVERSION
# ──────────────────────────────────────────────────────────────────────────────

def parse_result(result: dict, city_slug: str, activity_id: int) -> dict | None:
    """
    Convertit un résultat SerpAPI en entrée fixture JSON.
    Retourne None si le résultat doit être ignoré.
    """
    title    = result.get("title", "").strip()
    gtype    = result.get("type", "")
    rating   = result.get("rating")
    reviews  = result.get("reviews")
    coords   = result.get("gps_coordinates", {})
    address  = result.get("address", "")

    if not title:
        return None

    # Exclure les types non touristiques
    if is_excluded(gtype):
        return None

    # Filtre qualité minimale
    if rating is not None and float(rating) < MIN_RATING:
        return None

    # Coordonnées GPS
    lat = coords.get("latitude") if coords else None
    lng = coords.get("longitude") if coords else None
    has_geo = lat is not None and lng is not None

    # Enrichissement du nom FR (ajout du contexte si adresse disponible)
    name_fr = title
    if address:
        # Garder seulement la partie pertinente de l'adresse
        addr_short = address.split(",")[0].strip()
        if addr_short.lower() not in title.lower():
            name_fr = f"{title} - {addr_short}"

    activity_type = map_activity_type(gtype)

    return {
        "id":                   f"{city_slug}_{activity_id}",
        "name":                 title,
        "name_fr":              name_fr,
        "name_ar":              None,
        "lat":                  round(lat, 6) if lat else None,
        "lng":                  round(lng, 6) if lng else None,
        "activity_type":        activity_type,
        "place_type":           gtype if gtype else "Points of Interest",
        "is_core_tag":          rating is not None and float(rating) >= 4.0,
        "source":               "serpapi",
        "business_score":       0.2,
        "has_geospatial_info":  has_geo,
        "tripadvisor_rating":   round(float(rating), 1) if rating else None,
        "tripadvisor_reviews":  int(reviews) if reviews else None,
        "osm_tags":             {},
    }


# ──────────────────────────────────────────────────────────────────────────────
# ENRICHISSEMENT D'UNE VILLE
# ──────────────────────────────────────────────────────────────────────────────

def enrich_city(city_slug: str, city_info: dict, api_key: str) -> dict:
    """
    Enrichit le fichier fixture d'une ville avec des données SerpAPI.
    Retourne un résumé {added, skipped, total}.
    """
    city_en = city_info["city_en"]
    print(f"\n📍 Traitement: {city_en} (Tier {city_info['tier']})")

    # Charger fichier existant
    try:
        fixture = load_fixture(city_slug)
    except FileNotFoundError:
        print(f"  ⚠️  Fichier manquant, création depuis zéro")
        fixture = {
            "city": city_info["city_fr"],
            "total": 0,
            "fetched_at": str(date.today()),
            "tier": city_info["tier"],
            "source": "serpapi",
            "activities": [],
        }

    existing_activities = fixture.get("activities", [])
    existing_names = {act.get("name", "") for act in existing_activities}

    # Récupérer toutes les sources
    raw_results = fetch_all_queries(city_en, api_key)
    print(f"  📦 {len(raw_results)} résultats bruts récupérés")

    # Déduplication et conversion
    next_id = get_next_id(city_slug, existing_activities)
    added   = 0
    skipped = 0
    seen_in_batch = set()

    for result in raw_results:
        title = result.get("title", "").strip()

        # Skip si déjà dans le fichier ou dans ce batch
        if is_duplicate(title, existing_names) or is_duplicate(title, seen_in_batch):
            skipped += 1
            continue

        parsed = parse_result(result, city_slug, next_id)
        if parsed is None:
            skipped += 1
            continue

        existing_activities.append(parsed)
        existing_names.add(title)
        seen_in_batch.add(title)
        next_id += 1
        added += 1

        if added >= MAX_NEW_PER_CITY:
            print(f"  🔒 Limite {MAX_NEW_PER_CITY} nouvelles activités atteinte")
            break

    # Mettre à jour la source dans le header
    sources = set(fixture.get("source", "").split("+"))
    sources.add("serpapi")
    fixture["source"] = "+".join(sorted(s for s in sources if s))
    fixture["activities"] = existing_activities

    # Sauvegarder
    save_fixture(city_slug, fixture)

    return {"added": added, "skipped": skipped, "total": len(existing_activities)}


# ──────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enrichit les fixtures ZenifyTrip avec SerpAPI Google Maps"
    )
    parser.add_argument(
        "--key",
        default=os.getenv("SERPAPI_KEY", ""),
        help="Clé API SerpAPI (ou set SERPAPI_KEY dans .env)",
    )
    parser.add_argument(
        "--city",
        nargs="+",
        default=["all"],
        help="Slug(s) de ville à traiter, ou 'all' pour toutes (ex: sousse djerba)",
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        help="Filtrer par tier (1, 2 ou 3)",
    )
    args = parser.parse_args()

    api_key = args.key.strip()
    if not api_key:
        print("❌ Clé SerpAPI manquante. Utilise --key ou set SERPAPI_KEY=...")
        return

    # Sélection des villes
    if args.city == ["all"]:
        targets = dict(CITIES)
    else:
        targets = {slug: CITIES[slug] for slug in args.city if slug in CITIES}
        unknown = [s for s in args.city if s not in CITIES]
        if unknown:
            print(f"⚠️  Villes inconnues ignorées: {unknown}")

    if args.tier:
        targets = {k: v for k, v in targets.items() if v["tier"] == args.tier}

    print(f"\n🚀 ZenifyTrip SerpAPI Fetcher")
    print(f"   Villes cibles   : {len(targets)}")
    print(f"   Delay requêtes  : {REQUESTS_DELAY}s")
    print(f"   Max new/ville   : {MAX_NEW_PER_CITY}")
    print(f"   Rating minimum  : {MIN_RATING}")
    print("─" * 50)

    total_added   = 0
    total_skipped = 0

    for city_slug, city_info in targets.items():
        try:
            result = enrich_city(city_slug, city_info, api_key)
            total_added   += result["added"]
            total_skipped += result["skipped"]
            print(f"  → +{result['added']} ajoutées, {result['skipped']} ignorées, {result['total']} total")
        except Exception as e:
            print(f"  ❌ Erreur pour {city_slug}: {e}")

        time.sleep(REQUESTS_DELAY)

    print("\n" + "═" * 50)
    print(f"✅ Terminé — {total_added} activités ajoutées, {total_skipped} ignorées")
    print("═" * 50)


if __name__ == "__main__":
    main()
