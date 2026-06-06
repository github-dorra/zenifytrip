"""
Table statique des destinations tunisiennes par aéroport.
Utilisée par flight_service pour enrichir les candidats vols.
Données vérifiées — ne pas ajouter sans confirmation.

Structure par entrée :
  city               : nom de la ville
  region             : zone géographique
  vibe               : ambiance dominante (liste)
  tags               : mots-clés pour matching semantic_node
  highlights         : attractions principales confirmées
  traveler_type      : profils voyageurs adaptés
  best_months        : mois idéaux (1=jan ... 12=dec)
  avoid_months       : mois à éviter
  nearest_airport    : (destinations terrestres uniquement) code IATA aéroport le plus proche
"""

import unicodedata
from typing import Optional


TUNISIA_DESTINATIONS = {

    # ----------------------------------------------------------------
    # TUNIS — Capitale
    # ----------------------------------------------------------------
    "TUN": {
        "city": "Tunis",
        "region": "Nord — Côte",
        "vibe": ["culture", "histoire", "ville", "gastronomie", "business"],
        "tags": [
            "capitale", "medina", "histoire", "culture", "musée",
            "carthage", "patrimoine", "gastronomie", "shopping",
            "sidi-bou-said", "bardo", "ville", "business",
        ],
        "highlights": [
            "Médina de Tunis (UNESCO)",
            "Musée du Bardo",
            "Ruines de Carthage",
            "Sidi Bou Saïd",
            "Souks de la médina",
        ],
        "traveler_type": ["culturel", "business", "solo", "couple", "famille"],
        "best_months": [3, 4, 5, 9, 10, 11],
        "avoid_months": [7, 8],
    },

    # ----------------------------------------------------------------
    # DJERBA — Île du Sud
    # ----------------------------------------------------------------
    "DJE": {
        "city": "Djerba",
        "region": "Sud — Île Méditerranée",
        "vibe": ["plage", "détente", "famille", "culture", "resort"],
        "tags": [
            "île", "plage", "famille", "resort", "détente", "soleil",
            "el-ghriba", "houmt-souk", "snorkeling", "méditerranée",
            "artisanat", "poterie", "synagogue",
        ],
        "highlights": [
            "Synagogue El Ghriba (plus ancienne d'Afrique)",
            "Houmt Souk — marché traditionnel",
            "Zone touristique — plages",
            "Village de Guellala — poterie",
            "Musée de Guellala",
        ],
        "traveler_type": ["famille", "couple", "détente", "culturel"],
        "best_months": [5, 6, 7, 8, 9, 10],
        "avoid_months": [12, 1, 2],
    },

    # ----------------------------------------------------------------
    # MONASTIR — Côte du Sahel
    # ----------------------------------------------------------------
    "MIR": {
        "city": "Monastir",
        "region": "Centre-Est — Sahel",
        "vibe": ["plage", "histoire", "détente", "golf", "marina"],
        "tags": [
            "plage", "ribat", "histoire", "marina", "golf", "détente",
            "bourguiba", "sahel", "balnéaire", "couple", "resort",
        ],
        "highlights": [
            "Ribat de Monastir (forteresse, site de tournage)",
            "Mausolée Habib Bourguiba",
            "Marina de Monastir",
            "Plages de Skanes",
            "Musée du costume traditionnel",
        ],
        "traveler_type": ["couple", "famille", "culturel", "golf"],
        "best_months": [5, 6, 7, 8, 9, 10],
        "avoid_months": [12, 1, 2],
    },

    # ----------------------------------------------------------------
    # TOZEUR — Sahara
    # ----------------------------------------------------------------
    "TOE": {
        "city": "Tozeur",
        "region": "Sud-Ouest — Désert",
        "vibe": ["aventure", "désert", "nature", "insolite", "découverte"],
        "tags": [
            "désert", "aventure", "sahara", "oasis", "star-wars",
            "chott-el-jerid", "4x4", "chameau", "dunes", "sel",
            "palmiers", "insolite", "nature", "coucher-soleil",
        ],
        "highlights": [
            "Chott el-Jerid (lac de sel)",
            "Sites de tournage Star Wars",
            "Oasis de Chebika, Tamerza, Mides",
            "Musée Dar Chrait",
            "Balades en 4x4 et à dos de chameau",
        ],
        "traveler_type": ["aventure", "solo", "couple", "découverte"],
        "best_months": [10, 11, 12, 1, 2, 3, 4],
        "avoid_months": [6, 7, 8],
    },

    # ----------------------------------------------------------------
    # TABARKA — Nord-Ouest
    # ----------------------------------------------------------------
    "TBJ": {
        "city": "Tabarka",
        "region": "Nord-Ouest — Côte corallienne",
        "vibe": ["nature", "plongée", "musique", "écotourisme", "détente"],
        "tags": [
            "plongée", "corail", "nature", "jazz", "festival",
            "forêt", "mer", "écotourisme", "fort-génois", "calme",
            "randonnée", "pêche",
        ],
        "highlights": [
            "Plongée sous-marine — corail rouge",
            "Festival international de jazz (juillet)",
            "Fort génois",
            "Forêts de chênes-lièges",
            "Musée archéologique",
        ],
        "traveler_type": ["plongée", "nature", "musique", "couple", "solo"],
        "best_months": [6, 7, 8, 9],
        "avoid_months": [12, 1, 2],
    },

    # ----------------------------------------------------------------
    # SFAX — Centre industriel
    # ----------------------------------------------------------------
    "SFA": {
        "city": "Sfax",
        "region": "Centre-Est",
        "vibe": ["culture", "médina", "authentique", "local"],
        "tags": [
            "médina", "authentique", "local", "artisanat", "huile-olive",
            "kerkennah", "île", "pêche", "culture",
        ],
        "highlights": [
            "Médina de Sfax (bien conservée)",
            "Îles Kerkennah",
            "Musée régional",
            "Marché central",
        ],
        "traveler_type": ["culturel", "authentique", "solo"],
        "best_months": [3, 4, 5, 9, 10, 11],
        "avoid_months": [7, 8],
    },

    # ----------------------------------------------------------------
    # SOUSSE — Sahel balnéaire
    # ----------------------------------------------------------------
    "SUF": {
        "city": "Sousse",
        "region": "Centre-Est — Sahel",
        "vibe": ["plage", "animation", "nightlife", "resort", "famille"],
        "tags": [
            "plage", "resort", "médina", "port-el-kantaoui", "animation",
            "nightlife", "jeunes", "famille", "aquapark", "marina", "sahel",
            "sousse", "balnéaire", "shopping",
        ],
        "highlights": [
            "Médina de Sousse (UNESCO)",
            "Port El Kantaoui — marina et resort",
            "Grande Mosquée de Sousse",
            "Musée archéologique de Sousse",
            "Aquapark",
        ],
        "traveler_type": ["famille", "couple", "jeunes", "animation"],
        "best_months": [5, 6, 7, 8, 9, 10],
        "avoid_months": [12, 1, 2],
    },

    # ----------------------------------------------------------------
    # HAMMAMET / NABEUL — Cap Bon (aéroport Enfidha)
    # ----------------------------------------------------------------
    "NBE": {
        "city": "Hammamet / Nabeul",
        "region": "Nord-Est — Cap Bon",
        "vibe": ["plage", "détente", "resort", "nature", "artisanat"],
        "tags": [
            "plage", "resort", "jasmin", "poterie", "cap-bon", "hammamet",
            "nabeul", "nature", "calme", "famille", "yasmine-hammamet",
            "ceramique", "détente", "vignobles",
        ],
        "highlights": [
            "Yasmine Hammamet — zone touristique",
            "Nabeul — capitale de la poterie et du jasmin",
            "Cap Bon — vignobles et nature",
            "Médina de Hammamet",
            "Aquapark Carthageland",
        ],
        "traveler_type": ["famille", "couple", "détente", "nature"],
        "best_months": [5, 6, 7, 8, 9, 10],
        "avoid_months": [12, 1, 2],
    },

    # ----------------------------------------------------------------
    # GABÈS — Oasis maritime
    # ----------------------------------------------------------------
    "GAF": {
        "city": "Gabès",
        "region": "Sud-Est — Oasis maritime",
        "vibe": ["authentique", "nature", "local", "aventure", "oasis"],
        "tags": [
            "oasis", "mer", "authentique", "local", "matmata", "berbère",
            "troglodyte", "nature", "aventure", "palmiers", "gabès",
            "off-the-beaten-path",
        ],
        "highlights": [
            "Oasis maritime unique au monde",
            "Matmata — villages troglodytes berbères",
            "Marché traditionnel de Gabès",
            "Accès aux villages berbères du Sud",
            "Chenini Gabès",
        ],
        "traveler_type": ["aventure", "culturel", "solo", "authentique"],
        "best_months": [3, 4, 5, 10, 11],
        "avoid_months": [7, 8],
    },

}


# ----------------------------------------------------------------
# Lookup helpers (existants — ne pas modifier)
# ----------------------------------------------------------------

def get_destination(iata_code: str) -> dict:
    """Retourne les données d'une destination par code IATA. {} si inconnue."""
    return TUNISIA_DESTINATIONS.get((iata_code or "").upper(), {})


def get_tags(iata_code: str) -> list:
    """Retourne les tags d'une destination pour matching sémantique."""
    return get_destination(iata_code).get("tags", [])


def get_best_months(iata_code: str) -> list:
    """Retourne les mois idéaux pour une destination."""
    return get_destination(iata_code).get("best_months", [])


def is_good_month(iata_code: str, month: int) -> bool:
    """True si le mois est recommandé pour cette destination."""
    dest = get_destination(iata_code)
    avoid = dest.get("avoid_months", [])
    return month not in avoid


# ----------------------------------------------------------------
# CITY_TO_IATA — résolution texte ville → code IATA
# 133 entrées organisées par région
# ----------------------------------------------------------------

CITY_TO_IATA: dict = {

    # ── GRAND TUNIS ──────────────────────────────────────────────
    "tunis": "TUN",               "al tunis": "TUN",
    "carthage": "TUN",            "la marsa": "TUN",
    "la goulette": "TUN",         "sidi bou said": "TUN",
    "sidi-bou-said": "TUN",       "gammarth": "TUN",
    "le bardo": "TUN",            "bardo": "TUN",
    "bab el bhar": "TUN",         "ariana": "TUN",
    "ben arous": "TUN",           "manouba": "TUN",
    "ettadhamen": "TUN",          "raoued": "TUN",
    "l'aouina": "TUN",            "l aouina": "TUN",
    "kalaat el andalous": "TUN",  "hammam lif": "TUN",
    "hammam chott": "TUN",        "rades": "TUN",
    "megrine": "TUN",             "fouchana": "TUN",
    "el mourouj": "TUN",          "zaghouan": "TUN",
    "medjez el bab": "TUN",       "testour": "TUN",
    "dougga": "TUN",              "teboursouk": "TUN",
    "utique": "TUN",

    # ── NORD — BIZERTE ───────────────────────────────────────────
    "bizerte": "TUN",             "binzart": "TUN",
    "menzel bourguiba": "TUN",    "mateur": "TUN",
    "ras jebel": "TUN",           "menzel jemil": "TUN",
    "ghar el melh": "TUN",        "sejnane": "TBJ",

    # ── NORD — BÉJA ──────────────────────────────────────────────
    "beja": "TUN",                "béja": "TUN",
    "thibar": "TUN",              "nefza": "TBJ",
    "bou salem": "TUN",           "amdoun": "TBJ",

    # ── NORD-OUEST — JENDOUBA & TABARKA ──────────────────────────
    "tabarka": "TBJ",             "ain draham": "TBJ",
    "aïn draham": "TBJ",          "ain-draham": "TBJ",
    "jendouba": "TBJ",            "fernana": "TBJ",
    "bulla regia": "TBJ",         "ghardimaou": "TBJ",
    "oued melliz": "TBJ",         "cap serrat": "TBJ",

    # ── NORD-OUEST — KEF & SILIANA ────────────────────────────────
    "le kef": "TUN",              "kef": "TUN",
    "el kef": "TUN",              "dahmani": "TUN",
    "jerissa": "TUN",             "siliana": "TUN",
    "makthar": "TUN",             "maktar": "TUN",
    "sakiet sidi youssef": "TUN", "tajerouine": "TUN",
    "kalaat khasba": "TUN",       "nebeur": "TUN",
    "rouhia": "TUN",              "gaafour": "TUN",
    "le sers": "TUN",             "bou arada": "TUN",

    # ── CAP BON — NABEUL ─────────────────────────────────────────
    "nabeul": "NBE",              "hammamet": "NBE",
    "yasmine hammamet": "NBE",    "yasmine-hammamet": "NBE",
    "enfidha": "NBE",             "cap bon": "NBE",
    "cap-bon": "NBE",             "kelibia": "NBE",
    "korba": "NBE",               "menzel temime": "NBE",
    "el haouaria": "NBE",         "beni khiar": "NBE",
    "grombalia": "NBE",           "dar chaabane": "NBE",
    "hammam el ghezaz": "NBE",    "korbous": "TUN",
    "soliman": "TUN",

    # ── SAHEL — SOUSSE ───────────────────────────────────────────
    "sousse": "SUF",              "sus": "SUF",
    "port el kantaoui": "SUF",    "port-el-kantaoui": "SUF",
    "el kantaoui": "SUF",         "akouda": "SUF",
    "kalaa kebira": "SUF",        "hammam sousse": "SUF",
    "hergla": "SUF",              "sidi bou ali": "SUF",

    # ── SAHEL — MONASTIR ─────────────────────────────────────────
    "monastir": "MIR",            "skanes": "MIR",
    "ksar hellal": "MIR",         "moknine": "MIR",
    "jammel": "MIR",              "teboulba": "MIR",
    "bembla": "MIR",              "bekalta": "MIR",
    "sayada": "MIR",              "ouerdanine": "MIR",
    "msaken": "MIR",

    # ── ZAGHOUAN ─────────────────────────────────────────────────
    "zriba": "TUN",               "hammam zriba": "TUN",
    "thuburbo majus": "TUN",      "nadhour": "TUN",

    # ── MAHDIA ───────────────────────────────────────────────────
    "mahdia": "MIR",              "al mahdiyya": "MIR",
    "el jem": "MIR",              "el-jem": "MIR",
    "ksour essef": "MIR",         "salakta": "MIR",
    "chebba": "SFA",              "bou merdes": "MIR",
    "essouassi": "MIR",           "ouled chamekh": "MIR",

    # ── CENTRE — KAIROUAN ────────────────────────────────────────
    "kairouan": "MIR",            "al qayrawan": "MIR",
    "haffouz": "MIR",             "hajeb el ayoun": "MIR",
    "sbikha": "MIR",              "nasrallah": "MIR",
    "el alaa": "MIR",             "oueslatia": "MIR",
    "bou hajla": "MIR",

    # ── CENTRE — KASSERINE & SIDI BOUZID ─────────────────────────
    "kasserine": "SFA",           "sbeitla": "SFA",
    "feriana": "TOE",             "thala": "SFA",
    "sidi bouzid": "SFA",         "regueb": "SFA",
    "foussana": "SFA",            "haïdra": "SFA",
    "haidra": "SFA",              "thélepte": "SFA",
    "thelepte": "SFA",            "el ayoun": "SFA",
    "jelma": "SFA",               "bir el hafey": "SFA",
    "meknassy": "SFA",

    # ── CENTRE-EST — SFAX ────────────────────────────────────────
    "sfax": "SFA",                "safaqis": "SFA",
    "kerkennah": "SFA",           "iles kerkennah": "SFA",
    "sakiet ezzit": "SFA",        "el amra": "SFA",
    "jebiniana": "SFA",           "agareb": "SFA",
    "gremda": "SFA",              "chihia": "SFA",
    "skhira": "SFA",              "menzel chaker": "SFA",

    # ── SUD-EST — GABÈS ──────────────────────────────────────────
    "gabes": "GAF",               "gabès": "GAF",
    "matmata": "GAF",             "nouvelle matmata": "GAF",
    "el hamma": "GAF",            "mareth": "GAF",
    "metouia": "GAF",             "chenini gabes": "GAF",
    "ghannouch": "GAF",

    # ── SUD-EST — MÉDENINE & DJERBA ──────────────────────────────
    "djerba": "DJE",              "jerba": "DJE",
    "djerba-zarzis": "DJE",       "houmt souk": "DJE",
    "houmt-souk": "DJE",          "midoun": "DJE",
    "guellala": "DJE",            "ajim": "DJE",
    "el jorf": "DJE",             "sedouikech": "DJE",
    "medenine": "DJE",            "médenine": "DJE",
    "zarzis": "DJE",              "ben gardane": "DJE",
    "beni khedache": "DJE",       "ksar medenine": "DJE",
    "el kantara": "DJE",

    # ── SUD — TATAOUINE ──────────────────────────────────────────
    "tataouine": "DJE",           "tatawin": "DJE",
    "chenini": "DJE",             "douiret": "DJE",
    "ksar ouled soltane": "DJE",  "ghomrassen": "DJE",
    "remada": "DJE",              "ksar hadada": "DJE",
    "ksar haddada": "DJE",        "beni barka": "DJE",

    # ── SUD-OUEST — GAFSA ────────────────────────────────────────
    # (aéroport Gafsa sans vols réguliers → TOE le plus proche opérationnel)
    "gafsa": "TOE",               "metlaoui": "TOE",
    "moulares": "TOE",            "redeyef": "TOE",
    "el guettar": "TOE",          "sened": "TOE",

    # ── SUD-OUEST — TOZEUR ───────────────────────────────────────
    "tozeur": "TOE",              "nefta": "TOE",
    "degache": "TOE",             "chebika": "TOE",
    "tamerza": "TOE",             "mides": "TOE",
    "chott el jerid": "TOE",      "chott-el-jerid": "TOE",

    # ── SUD — KÉBILI & DOUZ ──────────────────────────────────────
    "douz": "TOE",                "kebili": "TOE",
    "kébili": "TOE",              "souk lahad": "TOE",
    "faouar": "TOE",              "el faouar": "TOE",

    # ── SITES TOURISTIQUES MAJEURS ────────────────────────────────
    "ksar ghilane": "TOE",        "ichkeul": "TUN",
    "ichkeul national park": "TUN", "parc ichkeul": "TUN",
}


# ----------------------------------------------------------------
# CITY_TO_AIRPORTS — villes sans aéroport + régions
# Plusieurs aéroports ordonnés par distance croissante
# Fallback vers CITY_TO_IATA si ville non présente ici
# ----------------------------------------------------------------

CITY_TO_AIRPORTS: dict = {

    # ── GRAND TUNIS ──────────────────────────────────────────────
    "grand tunis":        [{"iata": "TUN", "distance_km": 10,  "label": "Tunis-Carthage"}],
    "tunis":              [{"iata": "TUN", "distance_km": 8,   "label": "Tunis-Carthage"}],

    # ── NORD — BÉJA ──────────────────────────────────────────────
    "beja":               [{"iata": "TUN", "distance_km": 90,  "label": "Tunis-Carthage"},
                           {"iata": "TBJ", "distance_km": 100, "label": "Tabarka"}],
    "béja":               [{"iata": "TUN", "distance_km": 90,  "label": "Tunis-Carthage"},
                           {"iata": "TBJ", "distance_km": 100, "label": "Tabarka"}],
    "siliana":            [{"iata": "TUN", "distance_km": 120, "label": "Tunis-Carthage"},
                           {"iata": "MIR", "distance_km": 130, "label": "Monastir"}],
    "zaghouan":           [{"iata": "TUN", "distance_km": 65,  "label": "Tunis-Carthage"},
                           {"iata": "NBE", "distance_km": 80,  "label": "Enfidha-Hammamet"}],

    # ── NORD-OUEST — JENDOUBA ────────────────────────────────────
    "jendouba":           [{"iata": "TBJ", "distance_km": 75,  "label": "Tabarka"},
                           {"iata": "TUN", "distance_km": 150, "label": "Tunis-Carthage"}],

    # ── NORD-OUEST — KEF ─────────────────────────────────────────
    "le kef":             [{"iata": "TUN", "distance_km": 170, "label": "Tunis-Carthage"}],
    "kef":                [{"iata": "TUN", "distance_km": 170, "label": "Tunis-Carthage"}],

    # ── CAP BON ──────────────────────────────────────────────────
    "hammamet":           [{"iata": "NBE", "distance_km": 20,  "label": "Enfidha-Hammamet"},
                           {"iata": "TUN", "distance_km": 65,  "label": "Tunis-Carthage"}],
    "nabeul":             [{"iata": "NBE", "distance_km": 25,  "label": "Enfidha-Hammamet"},
                           {"iata": "TUN", "distance_km": 70,  "label": "Tunis-Carthage"}],
    "kelibia":            [{"iata": "NBE", "distance_km": 60,  "label": "Enfidha-Hammamet"},
                           {"iata": "TUN", "distance_km": 80,  "label": "Tunis-Carthage"}],

    # ── SAHEL — SOUSSE ───────────────────────────────────────────
    "sousse":             [{"iata": "SUF", "distance_km": 30,  "label": "Enfidha-Sousse"},
                           {"iata": "MIR", "distance_km": 35,  "label": "Monastir"},
                           {"iata": "NBE", "distance_km": 60,  "label": "Enfidha-Hammamet"}],

    # ── MAHDIA ───────────────────────────────────────────────────
    "mahdia":             [{"iata": "MIR", "distance_km": 60,  "label": "Monastir"},
                           {"iata": "SUF", "distance_km": 80,  "label": "Enfidha-Sousse"}],
    "al mahdiyya":        [{"iata": "MIR", "distance_km": 60,  "label": "Monastir"},
                           {"iata": "SUF", "distance_km": 80,  "label": "Enfidha-Sousse"}],
    "el jem":             [{"iata": "MIR", "distance_km": 60,  "label": "Monastir"},
                           {"iata": "SFA", "distance_km": 60,  "label": "Sfax"},
                           {"iata": "SUF", "distance_km": 70,  "label": "Enfidha-Sousse"}],
    "el-jem":             [{"iata": "MIR", "distance_km": 60,  "label": "Monastir"},
                           {"iata": "SFA", "distance_km": 60,  "label": "Sfax"},
                           {"iata": "SUF", "distance_km": 70,  "label": "Enfidha-Sousse"}],

    # ── CENTRE — KAIROUAN ────────────────────────────────────────
    "kairouan":           [{"iata": "NBE", "distance_km": 60,  "label": "Enfidha-Hammamet"},
                           {"iata": "MIR", "distance_km": 65,  "label": "Monastir"},
                           {"iata": "SUF", "distance_km": 70,  "label": "Enfidha-Sousse"}],
    "al qayrawan":        [{"iata": "NBE", "distance_km": 60,  "label": "Enfidha-Hammamet"},
                           {"iata": "MIR", "distance_km": 65,  "label": "Monastir"},
                           {"iata": "SUF", "distance_km": 70,  "label": "Enfidha-Sousse"}],

    # ── CENTRE — KASSERINE & SIDI BOUZID ─────────────────────────
    "kasserine":          [{"iata": "SFA", "distance_km": 160, "label": "Sfax"},
                           {"iata": "TUN", "distance_km": 240, "label": "Tunis-Carthage"}],
    "sbeitla":            [{"iata": "SFA", "distance_km": 130, "label": "Sfax"},
                           {"iata": "TOE", "distance_km": 180, "label": "Tozeur"}],
    "sidi bouzid":        [{"iata": "SFA", "distance_km": 90,  "label": "Sfax"},
                           {"iata": "MIR", "distance_km": 120, "label": "Monastir"}],
    "gafsa":              [{"iata": "TOE", "distance_km": 100, "label": "Tozeur"},
                           {"iata": "SFA", "distance_km": 180, "label": "Sfax"}],

    # ── SUD-EST — MÉDENINE & TATAOUINE ───────────────────────────
    "medenine":           [{"iata": "DJE", "distance_km": 75,  "label": "Djerba-Zarzis"},
                           {"iata": "GAF", "distance_km": 75,  "label": "Gabès"}],
    "médenine":           [{"iata": "DJE", "distance_km": 75,  "label": "Djerba-Zarzis"},
                           {"iata": "GAF", "distance_km": 75,  "label": "Gabès"}],
    "tataouine":          [{"iata": "GAF", "distance_km": 120, "label": "Gabès"},
                           {"iata": "DJE", "distance_km": 160, "label": "Djerba-Zarzis"}],
    "tatawin":            [{"iata": "GAF", "distance_km": 120, "label": "Gabès"},
                           {"iata": "DJE", "distance_km": 160, "label": "Djerba-Zarzis"}],

    # ── SUD — KÉBILI & DOUZ ──────────────────────────────────────
    "douz":               [{"iata": "TOE", "distance_km": 100, "label": "Tozeur"}],
    "kebili":             [{"iata": "TOE", "distance_km": 100, "label": "Tozeur"}],
    "kébili":             [{"iata": "TOE", "distance_km": 100, "label": "Tozeur"}],
    "ksar ghilane":       [{"iata": "TOE", "distance_km": 160, "label": "Tozeur"},
                           {"iata": "DJE", "distance_km": 200, "label": "Djerba-Zarzis"}],

    # ── RÉGIONS ──────────────────────────────────────────────────
    "nord":               [{"iata": "TUN", "distance_km": 80,  "label": "Tunis-Carthage"},
                           {"iata": "TBJ", "distance_km": 5,   "label": "Tabarka"}],
    "nord-ouest":         [{"iata": "TBJ", "distance_km": 5,   "label": "Tabarka"},
                           {"iata": "TUN", "distance_km": 150, "label": "Tunis-Carthage"}],
    "cap bon":            [{"iata": "NBE", "distance_km": 30,  "label": "Enfidha-Hammamet"},
                           {"iata": "TUN", "distance_km": 70,  "label": "Tunis-Carthage"}],
    "sahel":              [{"iata": "SUF", "distance_km": 0,   "label": "Enfidha-Sousse"},
                           {"iata": "MIR", "distance_km": 5,   "label": "Monastir"},
                           {"iata": "NBE", "distance_km": 60,  "label": "Enfidha-Hammamet"}],
    "centre":             [{"iata": "MIR", "distance_km": 65,  "label": "Monastir"},
                           {"iata": "SFA", "distance_km": 160, "label": "Sfax"},
                           {"iata": "TUN", "distance_km": 150, "label": "Tunis-Carthage"}],
    "centre-est":         [{"iata": "SFA", "distance_km": 5,   "label": "Sfax"},
                           {"iata": "MIR", "distance_km": 60,  "label": "Monastir"}],
    "sud":                [{"iata": "DJE", "distance_km": 0,   "label": "Djerba-Zarzis"},
                           {"iata": "GAF", "distance_km": 5,   "label": "Gabès"},
                           {"iata": "TOE", "distance_km": 5,   "label": "Tozeur"}],
    "sud-est":            [{"iata": "DJE", "distance_km": 0,   "label": "Djerba-Zarzis"},
                           {"iata": "GAF", "distance_km": 5,   "label": "Gabès"}],
    "sud-ouest":          [{"iata": "TOE", "distance_km": 0,   "label": "Tozeur"}],
    "desert":             [{"iata": "TOE", "distance_km": 0,   "label": "Tozeur"},
                           {"iata": "DJE", "distance_km": 200, "label": "Djerba-Zarzis"}],
    "désert":             [{"iata": "TOE", "distance_km": 0,   "label": "Tozeur"},
                           {"iata": "DJE", "distance_km": 200, "label": "Djerba-Zarzis"}],
}


# ----------------------------------------------------------------
# Helper interne — normalisation accents + casse
# ----------------------------------------------------------------

def _normalize(text: str) -> str:
    text = text.strip().lower()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ----------------------------------------------------------------
# FONCTION 1 — city_to_iata
# ----------------------------------------------------------------

def city_to_iata(city_text: str) -> Optional[str]:
    """
    Résout un texte ville en code IATA.
    Matching insensible à la casse et aux accents.
    Retourne None si la ville est inconnue.

    Exemples :
        city_to_iata("jerba")     → "DJE"
        city_to_iata("Kairouan") → "MIR"
        city_to_iata("douz")      → "TOE"
    """
    if not city_text:
        return None
    return CITY_TO_IATA.get(_normalize(city_text))


# ----------------------------------------------------------------
# FONCTION 2 — city_to_airports
# ----------------------------------------------------------------

def city_to_airports(city_text: str) -> list:
    """
    Retourne la liste des aéroports proches d'une ville ou région.
    Triée par distance croissante.

    Cherche d'abord dans CITY_TO_AIRPORTS (plusieurs options).
    Fallback vers CITY_TO_IATA si ville non présente (un seul aéroport).
    Retourne [] si ville inconnue.

    Exemples :
        city_to_airports("kairouan")
        → [{"iata": "NBE", "distance_km": 60, "label": "Enfidha-Hammamet"},
           {"iata": "MIR", "distance_km": 65, "label": "Monastir"},
           {"iata": "SUF", "distance_km": 70, "label": "Enfidha-Sousse"}]

        city_to_airports("sahel")
        → [{"iata": "SUF", ...}, {"iata": "MIR", ...}, {"iata": "NBE", ...}]

        city_to_airports("douz")
        → [{"iata": "TOE", "distance_km": 100, "label": "Tozeur"}]
    """
    if not city_text:
        return []

    normalized = _normalize(city_text)

    # 1. Cherche dans CITY_TO_AIRPORTS (plusieurs options avec distances)
    airports = CITY_TO_AIRPORTS.get(normalized)
    if airports:
        return sorted(airports, key=lambda x: x.get("distance_km") or 9999)

    # 2. Fallback CITY_TO_IATA (un seul aéroport, distance inconnue)
    iata = CITY_TO_IATA.get(normalized)
    if iata:
        return [{"iata": iata, "distance_km": None, "label": None}]

    return []


# ----------------------------------------------------------------
# FONCTION 3 — get_seasonal_advice
# ----------------------------------------------------------------

_MONTH_NAMES = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}


def get_seasonal_advice(iata: str, travel_month: int) -> dict:
    """
    Retourne un conseil saisonnier pour une destination et un mois donné.
    Utilise travel_month fourni — jamais datetime.now().

    Retourne :
        {"recommended": bool, "reason": str}
    """
    dest = get_destination(iata)
    if not dest:
        return {"recommended": True, "reason": "Destination non répertoriée dans notre base."}

    city       = dest.get("city", iata)
    vibe       = dest.get("vibe", [])
    avoid      = dest.get("avoid_months", [])
    best       = dest.get("best_months", [])
    month_name = _MONTH_NAMES.get(travel_month, str(travel_month))

    if travel_month in avoid:
        if "désert" in vibe or "aventure" in vibe:
            reason = (f"{city} est déconseillée en {month_name} : "
                      f"températures extrêmes pouvant dépasser 45°C.")
        elif "plage" in vibe or "resort" in vibe:
            reason = (f"{city} est déconseillée en {month_name} : "
                      f"temps froid, mer agitée et peu d'animation.")
        else:
            reason = (f"{city} est déconseillée en {month_name} : "
                      f"conditions climatiques défavorables.")
        return {"recommended": False, "reason": reason}

    if travel_month in best:
        highlights = dest.get("highlights", [])
        highlight  = highlights[0] if highlights else city
        if "plage" in vibe:
            reason = (f"{city} est idéale en {month_name} : "
                      f"mer chaude et plein soleil. À voir : {highlight}.")
        elif "désert" in vibe:
            reason = (f"{city} est idéale en {month_name} : "
                      f"températures douces, parfait pour {highlight}.")
        elif "spirituel" in vibe or "histoire" in vibe:
            reason = (f"{city} est idéale en {month_name} : "
                      f"climat agréable pour explorer {highlight}.")
        else:
            reason = (f"{city} est idéale en {month_name} : "
                      f"période optimale. À voir : {highlight}.")
        return {"recommended": True, "reason": reason}

    return {
        "recommended": True,
        "reason": f"{city} en {month_name} : période correcte pour visiter.",
    }


# ----------------------------------------------------------------
# FONCTION 3 — destination_features
# ----------------------------------------------------------------

def destination_features(iata: str) -> dict:
    """
    Retourne les features brutes d'une destination pour le Ranking Agent.
    Ne calcule aucun score — données brutes uniquement.

    Retourne :
        traveler_types, tags, vibe, best_months, avoid_months,
        nearest_airport (si applicable)
    """
    dest = get_destination(iata)
    if not dest:
        return {}

    result = {
        "traveler_types": dest.get("traveler_type", []),
        "tags":           dest.get("tags", []),
        "vibe":           dest.get("vibe", []),
        "best_months":    dest.get("best_months", []),
        "avoid_months":   dest.get("avoid_months", []),
    }
    if "nearest_airport" in dest:
        result["nearest_airport"] = dest["nearest_airport"]

    return result


# ----------------------------------------------------------------
# FONCTION 4 — get_recommendation_reason
# ----------------------------------------------------------------

def get_recommendation_reason(iata: str, travel_month: int) -> str:
    """
    Génère une phrase courte en français (max 2 lignes)
    justifiant pourquoi visiter cette destination ce mois-là.
    Utilise travel_month fourni — jamais datetime.now().
    """
    dest = get_destination(iata)
    if not dest:
        return "Destination disponible pour votre voyage."

    city       = dest.get("city", iata)
    vibe       = dest.get("vibe", [])
    highlights = dest.get("highlights", [])
    avoid      = dest.get("avoid_months", [])
    best       = dest.get("best_months", [])
    highlight  = highlights[0] if highlights else city
    month_name = _MONTH_NAMES.get(travel_month, str(travel_month))

    if travel_month in avoid:
        best_str = ", ".join(_MONTH_NAMES[m] for m in best[:3] if m in _MONTH_NAMES)
        return (f"{city} est déconseillée en {month_name}. "
                f"Préférez : {best_str}.")

    if travel_month in best:
        if "plage" in vibe:
            return (f"{city} en {month_name} : mer idéale et plein soleil. "
                    f"À voir : {highlight}.")
        if "désert" in vibe:
            return (f"{city} en {month_name} : températures parfaites pour le désert. "
                    f"À voir : {highlight}.")
        if "spirituel" in vibe or "religieux" in vibe:
            return (f"{city} en {month_name} : climat doux, idéal pour {highlight}.")
        if "culture" in vibe or "histoire" in vibe:
            return (f"{city} en {month_name} : climat agréable pour explorer {highlight}.")
        return (f"{city} en {month_name} : période idéale. À voir : {highlight}.")

    return (f"{city} en {month_name} : période correcte pour visiter. "
            f"À voir : {highlight}.")
