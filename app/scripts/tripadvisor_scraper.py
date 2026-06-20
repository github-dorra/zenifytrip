"""
Scraper TripAdvisor → MongoDB Atlas
====================================
Workflow :
  1. Appeler `scrape_city(city_key)` → navigue via Chrome MCP (manuel ou playwright)
  2. OU appeler `save_page_text(city_key, raw_text)` avec le texte récupéré via get_page_text()
  3. Le parser extrait attractions + tours, les upserte dans MongoDB.

Usage direct (depuis le REPL ou un script) :
  from app.scripts.tripadvisor_scraper import save_page_text, CITIES
  save_page_text("sousse", raw_text)
"""

import re
import logging
from datetime import datetime, timezone
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from app.config.mongodb import activities_collection, ensure_indexes

logger = logging.getLogger(__name__)

# ─── Catalogue des villes tunisiennes ────────────────────────────────────────

CITIES: dict[str, dict] = {
    "monastir": {
        "name": "Monastir",
        "destination_id": "monastir",
        "country": "Tunisie",
        "region": "Centre-Est",
        "tripadvisor_geoid": "g297949",
        "url": "https://www.tripadvisor.fr/Attractions-g297949-Activities-Monastir_Monastir_Governorate.html",
        "airport_iata": "MIR",
    },
    "tunis": {
        "name": "Tunis",
        "destination_id": "tunis",
        "country": "Tunisie",
        "region": "Nord",
        "tripadvisor_geoid": "g293758",
        "url": "https://www.tripadvisor.fr/Attractions-g293758-Activities-Tunis_Tunis_Governorate.html",
        "airport_iata": "TUN",
    },
    "sousse": {
        "name": "Sousse",
        "destination_id": "sousse",
        "country": "Tunisie",
        "region": "Centre-Est",
        "tripadvisor_geoid": "g295401",
        "url": "https://www.tripadvisor.fr/Attractions-g295401-Activities-Sousse_Sousse_Governorate.html",
        "airport_iata": "SUF",
    },
    "djerba": {
        "name": "Djerba",
        "destination_id": "djerba",
        "country": "Tunisie",
        "region": "Sud-Est",
        "tripadvisor_geoid": "g297941",
        "url": "https://www.tripadvisor.fr/Attractions-g297941-Activities-Djerba_Island_Medenine_Governorate.html",
        "airport_iata": "DJE",
    },
    "hammamet": {
        "name": "Hammamet",
        "destination_id": "hammamet",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g297943",
        "url": "https://www.tripadvisor.fr/Attractions-g297943-Activities-Hammamet_Nabeul_Governorate.html",
        "airport_iata": "NBE",
    },
    "kairouan": {
        "name": "Kairouan",
        "destination_id": "kairouan",
        "country": "Tunisie",
        "region": "Centre",
        "tripadvisor_geoid": "g303925",
        "url": "https://www.tripadvisor.fr/Attractions-g303925-Activities-Kairouan_Kairouan_Governorate.html",
        "airport_iata": None,
    },
    "mahdia": {
        "name": "Mahdia",
        "destination_id": "mahdia",
        "country": "Tunisie",
        "region": "Centre-Est",
        "tripadvisor_geoid": "g297947",
        "url": "https://www.tripadvisor.fr/Attractions-g297947-Activities-Mahdia_Mahdia_Governorate.html",
        "airport_iata": None,
    },
    "sfax": {
        "name": "Sfax",
        "destination_id": "sfax",
        "country": "Tunisie",
        "region": "Centre-Est",
        "tripadvisor_geoid": "g317087",
        "url": "https://www.tripadvisor.fr/Attractions-g317087-Activities-Sfax_Sfax_Governorate.html",
        "airport_iata": "SFA",
    },
    "tozeur": {
        "name": "Tozeur",
        "destination_id": "tozeur",
        "country": "Tunisie",
        "region": "Sud-Ouest",
        "tripadvisor_geoid": "g293757",
        "url": "https://www.tripadvisor.fr/Attractions-g293757-Activities-Tozeur_Tozeur_Governorate.html",
        "airport_iata": "TOE",
    },
    "tabarka": {
        "name": "Tabarka",
        "destination_id": "tabarka",
        "country": "Tunisie",
        "region": "Nord-Ouest",
        "tripadvisor_geoid": "g297953",
        "url": "https://www.tripadvisor.fr/Attractions-g297953-Activities-Tabarka_Jendouba_Governorate.html",
        "airport_iata": "TBJ",
    },
    "nabeul": {
        "name": "Nabeul",
        "destination_id": "nabeul",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g317086",
        "url": "https://www.tripadvisor.fr/Attractions-g317086-Activities-Nabeul_Nabeul_Governorate.html",
        "airport_iata": "NBE",
    },
    "bizerte": {
        "name": "Bizerte",
        "destination_id": "bizerte",
        "country": "Tunisie",
        "region": "Nord",
        "tripadvisor_geoid": "g480249",
        "url": "https://www.tripadvisor.fr/Attractions-g480249-Activities-Bizerte_Bizerte_Governorate.html",
        "airport_iata": None,
    },
    "beja": {
        "name": "Béja",
        "destination_id": "beja",
        "country": "Tunisie",
        "region": "Nord-Ouest",
        "tripadvisor_geoid": "g2629135",
        "url": "https://www.tripadvisor.fr/Attractions-g2629135-Activities-Beja_Governorate.html",
        "airport_iata": None,
    },
    "kef": {
        "name": "Le Kef",
        "destination_id": "kef",
        "country": "Tunisie",
        "region": "Nord-Ouest",
        "tripadvisor_geoid": "g946559",
        "url": "https://www.tripadvisor.fr/Attractions-g946559-Activities-Le_Kef_Le_Kef_Governorate.html",
        "airport_iata": None,
    },
    "jendouba": {
        "name": "Jendouba",
        "destination_id": "jendouba",
        "country": "Tunisie",
        "region": "Nord-Ouest",
        "tripadvisor_geoid": "g953410",
        "url": "https://www.tripadvisor.fr/Attractions-g953410-Activities-Jendouba_Jendouba_Governorate.html",
        "airport_iata": None,
    },
    "zaghouan": {
        "name": "Zaghouan",
        "destination_id": "zaghouan",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g844553",
        "url": "https://www.tripadvisor.fr/Attractions-g844553-Activities-Zaghouan_Zaghouan_Governorate.html",
        "airport_iata": None,
    },
    "siliana": {
        "name": "Siliana",
        "destination_id": "siliana",
        "country": "Tunisie",
        "region": "Nord-Ouest",
        "tripadvisor_geoid": "g2629161",
        "url": "https://www.tripadvisor.fr/Attractions-g2629161-Activities-Siliana_Governorate.html",
        "airport_iata": None,
    },
    "gabes": {
        "name": "Gabès",
        "destination_id": "gabes",
        "country": "Tunisie",
        "region": "Sud-Est",
        "tripadvisor_geoid": "g612360",
        "url": "https://www.tripadvisor.fr/Attractions-g612360-Activities-Gabes_Gabes_Governorate.html",
        "airport_iata": "GAE",
    },
    "gafsa": {
        "name": "Gafsa",
        "destination_id": "gafsa",
        "country": "Tunisie",
        "region": "Sud-Ouest",
        "tripadvisor_geoid": "g651644",
        "url": "https://www.tripadvisor.fr/Attractions-g651644-Activities-Gafsa_Gafsa_Governorate.html",
        "airport_iata": "GAF",
    },
    "tataouine": {
        "name": "Tataouine",
        "destination_id": "tataouine",
        "country": "Tunisie",
        "region": "Sud",
        "tripadvisor_geoid": "g477975",
        "url": "https://www.tripadvisor.fr/Attractions-g477975-Activities-Tataouine_Tataouine_Governorate.html",
        "airport_iata": None,
    },
    "medenine": {
        "name": "Médenine",
        "destination_id": "medenine",
        "country": "Tunisie",
        "region": "Sud-Est",
        "tripadvisor_geoid": "g2306339",
        "url": "https://www.tripadvisor.fr/Attractions-g2306339-Activities-Medenine_Medenine_Governorate.html",
        "airport_iata": None,
    },
    "kasserine": {
        "name": "Kasserine",
        "destination_id": "kasserine",
        "country": "Tunisie",
        "region": "Centre-Ouest",
        "tripadvisor_geoid": "g2629146",
        "url": "https://www.tripadvisor.fr/Attractions-g2629146-Activities-Kasserine_Governorate.html",
        "airport_iata": None,
    },
    "sidi_bouzid": {
        "name": "Sidi Bouzid",
        "destination_id": "sidi_bouzid",
        "country": "Tunisie",
        "region": "Centre",
        "tripadvisor_geoid": "g2629160",
        "url": "https://www.tripadvisor.fr/Attractions-g2629160-Activities-Sidi_Bouzid_Governorate.html",
        "airport_iata": None,
    },
    "sidi_bou_said": {
        "name": "Sidi Bou Said",
        "destination_id": "sidi_bou_said",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g316117",
        "url": "https://www.tripadvisor.fr/Attractions-g316117-Activities-Sidi_Bou_Said_Tunis_Governorate.html",
        "airport_iata": None,
    },
    "la_marsa": {
        "name": "La Marsa",
        "destination_id": "la_marsa",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g297946",
        "url": "https://www.tripadvisor.fr/Attractions-g297946-Activities-La_Marsa_Tunis_Governorate.html",
        "airport_iata": None,
    },
    "carthage": {
        "name": "Carthage",
        "destination_id": "carthage",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g293754",
        "url": "https://www.tripadvisor.fr/Attractions-g293754-Activities-Carthage_Tunis_Governorate.html",
        "airport_iata": None,
    },
    "la_goulette": {
        "name": "La Goulette",
        "destination_id": "la_goulette",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g946556",
        "url": "https://www.tripadvisor.fr/Attractions-g946556-Activities-La_Goulette_Tunis_Governorate.html",
        "airport_iata": None,
    },
    "ariana": {
        "name": "Ariana",
        "destination_id": "ariana",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g2629125",
        "url": "https://www.tripadvisor.fr/Attractions-g2629125-Activities-Ariana_Ariana_Governorate.html",
        "airport_iata": None,
    },
    "ben_arous": {
        "name": "Ben Arous",
        "destination_id": "ben_arous",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g2629179",
        "url": "https://www.tripadvisor.fr/Attractions-g2629179-Activities-Ben_Arous_Ben_Arous_Governorate.html",
        "airport_iata": None,
    },
    "douz": {
        "name": "Douz",
        "destination_id": "douz",
        "country": "Tunisie",
        "region": "Sud",
        "tripadvisor_geoid": "g477972",
        "url": "https://www.tripadvisor.fr/Attractions-g477972-Activities-Douz_Kebili_Governorate.html",
        "airport_iata": None,
    },
    "kebili": {
        "name": "Kébili",
        "destination_id": "kebili",
        "country": "Tunisie",
        "region": "Sud",
        "tripadvisor_geoid": "g1115268",
        "url": "https://www.tripadvisor.fr/Attractions-g1115268-Activities-Kebili_Kebili_Governorate.html",
        "airport_iata": None,
    },
    "matmata": {
        "name": "Matmata",
        "destination_id": "matmata",
        "country": "Tunisie",
        "region": "Sud-Est",
        "tripadvisor_geoid": "g293756",
        "url": "https://www.tripadvisor.fr/Attractions-g293756-Activities-Matmata_Gabes_Governorate.html",
        "airport_iata": None,
    },
    "zarzis": {
        "name": "Zarzis",
        "destination_id": "zarzis",
        "country": "Tunisie",
        "region": "Sud-Est",
        "tripadvisor_geoid": "g297945",
        "url": "https://www.tripadvisor.fr/Attractions-g297945-Activities-Zarzis_Medenine_Governorate.html",
        "airport_iata": None,
    },
    "nefta": {
        "name": "Nefta",
        "destination_id": "nefta",
        "country": "Tunisie",
        "region": "Sud-Ouest",
        "tripadvisor_geoid": "g297951",
        "url": "https://www.tripadvisor.fr/Attractions-g297951-Activities-Nefta_Tozeur_Governorate.html",
        "airport_iata": None,
    },
    "ain_draham": {
        "name": "Ain Draham",
        "destination_id": "ain_draham",
        "country": "Tunisie",
        "region": "Nord-Ouest",
        "tripadvisor_geoid": "g1791611",
        "url": "https://www.tripadvisor.fr/Attractions-g1791611-Activities-Ain_Draham_Jendouba_Governorate.html",
        "airport_iata": None,
    },
    "kelibia": {
        "name": "Kélibia",
        "destination_id": "kelibia",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g844554",
        "url": "https://www.tripadvisor.fr/Attractions-g844554-Activities-Kelibia_Nabeul_Governorate.html",
        "airport_iata": None,
    },
    "el_haouaria": {
        "name": "El Haouaria",
        "destination_id": "el_haouaria",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g482886",
        "url": "https://www.tripadvisor.fr/Attractions-g482886-Activities-El_Haouaria_Nabeul_Governorate.html",
        "airport_iata": None,
    },
    "korba": {
        "name": "Korba",
        "destination_id": "korba",
        "country": "Tunisie",
        "region": "Nord-Est",
        "tripadvisor_geoid": "g1506977",
        "url": "https://www.tripadvisor.fr/Attractions-g1506977-Activities-Korba_Nabeul_Governorate.html",
        "airport_iata": None,
    },
    "menzel_bourguiba": {
        "name": "Menzel Bourguiba",
        "destination_id": "menzel_bourguiba",
        "country": "Tunisie",
        "region": "Nord",
        "tripadvisor_geoid": "g1598714",
        "url": "https://www.tripadvisor.fr/Attractions-g1598714-Activities-Menzel_Bourguiba_Bizerte_Governorate.html",
        "airport_iata": None,
    },
    "sbeitla": {
        "name": "Sbeitla",
        "destination_id": "sbeitla",
        "country": "Tunisie",
        "region": "Centre-Ouest",
        "tripadvisor_geoid": "g946560",
        "url": "https://www.tripadvisor.fr/Attractions-g946560-Activities-Subaytilah_Kasserine_Governorate.html",
        "airport_iata": None,
    },
    "dougga": {
        "name": "Dougga",
        "destination_id": "dougga",
        "country": "Tunisie",
        "region": "Nord-Ouest",
        "tripadvisor_geoid": "g1237248",
        "url": "https://www.tripadvisor.fr/Attractions-g1237248-Activities-Teboursouk_Beja_Governorate.html",
        "airport_iata": None,
    },
}

# ─── Catégories → type (attraction vs tour) ──────────────────────────────────

ATTRACTION_CATEGORIES = {
    "ruines anciennes", "sites historiques", "marinas", "musées d'histoire",
    "parcs d'attractions", "parcs aquatiques", "musées spécialisés", "sites religieux",
    "plages", "sentiers équestres", "randonnées équestres", "parcours de golf",
    "spas", "salles de jeux", "boutiques", "bars et clubs", "îles", "clubs de gym",
    "camps sportifs", "circuits extrêmes", "monuments", "quartiers", "canyons",
    "plans d'eau", "zoos", "parcs nationaux", "marchés", "cafés", "bâtiments",
    "jardins", "trains touristiques", "déserts", "espaces naturels",
}

TOUR_CATEGORIES = {
    "expériences privées", "excursions d'une journée", "circuits d'une demi-journée",
    "circuits touristiques", "circuits historiques", "circuits de plusieurs jours",
    "visites en bus", "visites culturelles", "visites archéologiques", "visites à pied",
    "excursions en 4x4", "transferts", "croisières", "promenades à cheval",
    "safaris", "audioguides", "circuits rapides", "circuits de deux jours",
    "excursions nature", "activités pour enfants", "cours de cuisine", "camping",
}


def _is_tour(category: str) -> bool:
    cat = category.lower()
    for t in TOUR_CATEGORIES:
        if t in cat:
            return True
    return False


# ─── Parser du texte brut TripAdvisor ────────────────────────────────────────

def _parse_price(text: str) -> float | None:
    m = re.search(r"(\d[\d\s]*(?:,\d+)?)\s*€", text.replace(" ", "").replace(" ", ""))
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


def _parse_rating(text: str) -> float | None:
    m = re.search(r"\b([1-5](?:[.,]\d)?)\b", text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


def _parse_reviews(text: str) -> int | None:
    m = re.search(r"\((\d[\d\s]*)\s*avis?\)", text)
    if m:
        try:
            return int(m.group(1).replace(" ", ""))
        except ValueError:
            pass
    return None


def _infer_tags(name: str, category: str) -> list[str]:
    """Génère des tags sémantiques depuis le nom et la catégorie."""
    text = (name + " " + category).lower()
    tag_map = {
        "historique": ["musée", "ruines", "fort", "site", "médina", "ribat", "mausolée", "mosquée"],
        "culture": ["musée", "patrimoine", "costume", "traditionnel"],
        "religion": ["mosquée", "mosque", "mausolée", "marabout"],
        "plage": ["plage", "beach", "falaise", "palmiers"],
        "mer": ["marine", "marina", "bateau", "yacht", "île", "kuriat", "nautique"],
        "nature": ["canyon", "oasis", "désert", "sahara", "parc", "national"],
        "sport": ["golf", "karting", "karting", "quad", "4x4", "équitation", "cheval"],
        "bien-être": ["spa", "hammam", "massage", "réflexologie", "oxygen"],
        "famille": ["aquapark", "spring land", "enfants", "parc"],
        "aventure": ["4x4", "safari", "désert", "sahara", "paintball", "extrême"],
        "gastronomie": ["restaurant", "cuisine", "déjeuner", "repas"],
        "shopping": ["boutique", "souvenir", "marché", "folla"],
        "nightlife": ["bar", "club", "nocturne"],
        "Star Wars": ["star wars", "mos espa"],
    }
    tags = []
    for tag, keywords in tag_map.items():
        if any(kw in text for kw in keywords):
            tags.append(tag)
    return tags or ["divers"]


def _infer_traveler_types(tags: list[str], category: str) -> list[str]:
    mapping = {
        "famille": ["famille", "plage", "aquapark", "nature"],
        "couple": ["spa", "bien-être", "mer", "golf", "romantique"],
        "culture": ["historique", "culture", "religion"],
        "aventure": ["aventure", "sport", "4x4", "safari"],
        "solo": ["culture", "balade", "nature"],
        "jeunes": ["nightlife", "sport", "aventure"],
        "luxe": ["luxe", "VIP", "privé"],
    }
    types = []
    combined = tags + [category.lower()]
    for tt, keywords in mapping.items():
        if any(kw in " ".join(combined) for kw in keywords):
            types.append(tt)
    return types or ["tous profils"]


def parse_attractions_section(raw_text: str, city: dict) -> list[dict]:
    """
    Extrait la section 'Meilleures attractions' du texte brut TripAdvisor.
    Format attendu :
        {rank}. {Name}
        {rating}
        ({N} avis)
        {Category}
    """
    now = datetime.now(timezone.utc)
    docs = []

    # Pattern : numéro + nom (ex: "1. Forte El Ribat")
    pattern = re.compile(
        r"(\d+)\.\s+(.+?)\n"           # rank + name
        r"([\d,]+)?\n?"                 # rating (optionnel)
        r"(?:\((\d[\d\s]*)\s*\))?\n?"  # reviews (optionnel)
        r"([^\n]+)\n",                  # category
        re.MULTILINE,
    )

    for m in pattern.finditer(raw_text):
        rank     = int(m.group(1))
        name     = m.group(2).strip()
        rating   = float(m.group(3).replace(",", ".")) if m.group(3) else None
        reviews  = int(m.group(4).replace(" ", "")) if m.group(4) else None
        category = m.group(5).strip()

        if rank > 500 or not name:
            continue

        tags = _infer_tags(name, category)
        docs.append({
            "destination_id":   city["destination_id"],
            "destination":      city["name"],
            "country":          city["country"],
            "region":           city.get("region"),
            "name":             name,
            "type":             "attraction",
            "category":         category,
            "tripadvisor_rank": rank,
            "rating":           rating,
            "reviews_count":    reviews,
            "tags":             tags,
            "traveler_types":   _infer_traveler_types(tags, category),
            "price_from_eur":   None,
            "source":           "tripadvisor",
            "scraped_at":       now,
            "last_updated":     now,
        })

    return docs


def parse_tours_section(raw_text: str, city: dict) -> list[dict]:
    """
    Extrait les tours/expériences du texte brut TripAdvisor.
    Format attendu par bloc :
        {Name}
        {rating}
        ({N} avis)
        {Category}
        {lang} +N
        à partir de {price}€
    """
    now = datetime.now(timezone.utc)
    docs = []
    seen = set()

    # Repère les blocs "à partir de X€"
    price_positions = [m.start() for m in re.finditer(r"à partir de", raw_text)]

    for pos in price_positions:
        # Remonte ~300 chars avant pour trouver le nom
        start = max(0, pos - 350)
        block = raw_text[start:pos + 60]
        lines = [l.strip() for l in block.split("\n") if l.strip()]

        if not lines:
            continue

        # Le nom est souvent la première ligne non-numérique non-courte
        name = None
        category = None
        rating = None
        reviews = None
        for i, line in enumerate(lines):
            if re.match(r"^\d+\.", line):
                continue
            if len(line) > 8 and not re.match(r"^[\d,]+$", line) and "€" not in line:
                if name is None:
                    name = line
                elif category is None and len(line) > 4:
                    category = line
            if re.match(r"^[1-5][,.]?\d?$", line):
                rating = float(line.replace(",", "."))
            m = re.search(r"\((\d[\d\s]*)\s*\)", line)
            if m:
                reviews = int(m.group(1).replace(" ", ""))

        if not name or name in seen or len(name) < 6:
            continue

        price = _parse_price(raw_text[pos:pos + 80])
        seen.add(name)

        tags = _infer_tags(name, category or "")
        docs.append({
            "destination_id": city["destination_id"],
            "destination":    city["name"],
            "country":        city["country"],
            "region":         city.get("region"),
            "name":           name,
            "type":           "tour",
            "category":       category or "Expériences",
            "rating":         rating,
            "reviews_count":  reviews,
            "price_from_eur": price,
            "tags":           tags,
            "traveler_types": _infer_traveler_types(tags, category or ""),
            "source":         "tripadvisor",
            "scraped_at":     now,
            "last_updated":   now,
        })

    return docs


# ─── Upsert vers MongoDB ──────────────────────────────────────────────────────

def _bulk_upsert(col, docs: list[dict], key_fields: tuple) -> tuple[int, int]:
    if not docs:
        return 0, 0
    ops = [
        UpdateOne(
            {f: doc[f] for f in key_fields},
            {"$set": doc},
            upsert=True,
        )
        for doc in docs
    ]
    try:
        r = col.bulk_write(ops, ordered=False)
        return r.upserted_count, r.modified_count
    except BulkWriteError as e:
        logger.error(f"BulkWriteError: {e.details}")
        return 0, 0


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def save_page_text(city_key: str, raw_text: str) -> dict:
    """
    Parse le texte brut d'une page TripAdvisor et sauvegarde dans Atlas.

    Args:
        city_key : clé dans CITIES (ex: "sousse", "djerba")
        raw_text : contenu retourné par mcp__claude-in-chrome__get_page_text()

    Returns:
        Résumé {attractions_upserted, attractions_modified, tours_upserted, tours_modified}
    """
    if city_key not in CITIES:
        raise ValueError(f"Ville inconnue: {city_key}. Disponibles: {list(CITIES)}")

    ensure_indexes()
    city = CITIES[city_key]
    col  = activities_collection()

    attractions = parse_attractions_section(raw_text, city)
    tours       = parse_tours_section(raw_text, city)
    all_docs    = attractions + tours

    up, mod = _bulk_upsert(col, all_docs, ("name", "destination_id"))

    result = {
        "city":               city["name"],
        "attractions_parsed": len(attractions),
        "tours_parsed":       len(tours),
        "total_upserted":     up,
        "total_modified":     mod,
        "collection":         "activities_collection",
    }
    logger.info(f"[{city['name']}] {result}")
    return result


def get_city_url(city_key: str) -> str:
    """Retourne l'URL TripAdvisor à naviguer pour une ville."""
    return CITIES[city_key]["url"]
