"""
Enrichissement du champ activity_type pour les documents avec valeur "unknown".

Approche : inférence déterministe (0 token LLM) depuis name + description + tags + category.
Même pattern que la Phase 5 (enrich_semantic_rules).

Usage :
    python -m app.scripts.enrich_activity_type
    python -m app.scripts.enrich_activity_type --dry-run
"""
import argparse
import logging
import sys
from typing import Dict, List, Optional, Tuple

from pymongo import UpdateOne

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Règles enrichies — 5 types × mots-clés étendus (FR + EN + termes tunisiens)
# Chaque type est représenté par une liste de sous-listes (groupes thématiques)
# pour que la lecture reste maintenable.
# ──────────────────────────────────────────────────────────────────────────────
_TYPE_RULES: Dict[str, List[str]] = {

    "culture": [
        # Patrimoine islamique
        "mosquée", "mosque", "zaouïa", "zaouia", "médersa", "medersa", "méderse",
        "mausolée", "mausoleum", "minaret", "ribat", "ksar", "borj",
        # Patrimoine antique
        "archéologique", "archaeological", "ruines", "ruins", "amphithéâtre",
        "amphitheater", "forum", "thermes", "baths", "colisée", "colosseum",
        "carthaginois", "romain", "roman", "punique", "phénicien",
        "dougga", "sbeitla", "bulla", "kerkouane", "thuburbo", "uthina", "haidra",
        # Musées et lieux culturels
        "musée", "museum", "bardo", "galerie", "gallery", "exposition", "exhibition",
        "bibliothèque", "library", "centre culturel", "cultural center",
        # Art et artisanat
        "artisanat", "craft", "poterie", "pottery", "céramique", "ceramic",
        "mosaïque", "mosaic", "zellij", "broderie", "embroidery", "tapis", "carpet",
        "soufflage de verre", "ferronnerie", "sculpture", "calligraphie",
        # Médinas et médinas historiques
        "médina", "medina", "kasbah", "casbah", "ancienne ville", "old city",
        "ville historique", "historic", "historique", "vieille", "ancien", "old",
        # Monuments et bâtiments
        "monument", "palais", "palace", "château", "fort", "forteresse", "fortress",
        "tour", "tower", "porte", "gate", "arc", "arch", "colonne", "column",
        # Culture vivante
        "festival", "célébration", "tradition", "traditionnel", "local", "folklore",
        "musique", "music", "danse", "dance", "spectacle", "show", "concert",
        "patrimoine", "heritage", "civilisation", "histoire", "history",
        "synagogue", "église", "cathedral", "cathédrale", "basílique",
    ],

    "nature": [
        # Eau et littoral
        "plage", "beach", "mer", "sea", "côte", "coast", "littoral", "bord de mer",
        "snorkeling", "snorkelling", "plongée sous-marine",
        "île", "island", "archipel", "cap", "presqu'île", "péninsule",
        "falaise", "cliff", "baie", "bay", "lagune", "lagoon",
        # Désert et oasis
        "oasis", "désert", "desert", "sahara", "dune", "erg", "sable", "sand",
        "palmeraie", "palm grove", "dattier", "chott", "sebkha", "sel",
        "ksar", "troglodyte", "troglo",
        # Montagne et forêt
        "montagne", "mountain", "jebel", "djebel", "colline", "hill", "forêt", "forest",
        "pin", "pine", "chêne", "oak", "cèdre", "cedar", "maquis",
        "chambi", "zaghouan", "boukornine", "ichkeul",
        # Eau douce et zones humides
        "lac", "lake", "oued", "rivière", "river", "source", "spring",
        "marais", "wetland", "réserve", "reserve", "parc naturel", "national park",
        "parc", "park", "réserve naturelle", "nature reserve",
        # Grottes et spéléologie
        "grotte", "cave", "caverne", "spéléologie", "spelunking",
        # Paysages et panoramas
        "panorama", "vue", "view", "paysage", "landscape", "coucher de soleil",
        "sunset", "lever de soleil", "sunrise", "étoiles", "stars",
        # Écologie et faune
        "écologie", "ecology", "faune", "wildlife", "flore", "flora",
        "observation des oiseaux", "bird watching", "flamant", "flamingo",
        "jardin botanique", "botanical garden", "jardin", "garden",
    ],

    "adventure": [
        # Véhicules tout-terrain
        "quad", "4x4", "buggy", "moto", "motocross", "off-road",
        "safari", "caravane", "dromadaire", "chameau", "camel",
        # Sports nautiques
        "surf", "surfing", "kitesurf", "kiteboarding", "windsurf", "windsurfing",
        "jet ski", "jet-ski", "ski nautique", "wakeboard", "wakeboarding",
        "kayak", "paddle", "paddleboard", "voile", "sailing",
        "plongée", "diving", "scuba", "snorkel",
        # Sports terrestres
        "randonnée", "hiking", "trek", "trekking", "marche", "walking",
        "escalade", "climbing", "via ferrata", "canyoning",
        "vélo", "cycling", "vtt", "mountain bike",
        # Sports aériens
        "parapente", "paragliding", "deltaplane", "hang gliding",
        "parachute", "saut en parachute", "skydiving", "ulm",
        # Loisirs actifs
        "paintball", "karting", "karting", "laser game", "accrobranche",
        "tyrolienne", "zipline", "parcours aventure", "escape game",
        "bowling", "go-kart",
        # Équitation
        "cheval", "horse", "équitation", "horseback", "équestre",
        # Termes généraux
        "aventure", "adventure", "excursion", "expédition", "outdoor",
        "sport", "sports", "activité physique", "sensations fortes",
        "adrénaline", "extrême",
    ],

    "relax": [
        # Bien-être et soins
        "spa", "hammam", "massage", "massage traditionnel", "bain turc",
        "thalasso", "thalassothérapie", "thalassotherapy",
        "soin", "treatment", "beauté", "beauty", "détente", "relaxation",
        "bien-être", "wellness", "balnéo", "balnéothérapie",
        "sauna", "jacuzzi", "bain", "bain thermal", "thermal",
        "cure", "remise en forme", "fitness",
        # Pratiques douces
        "yoga", "méditation", "meditation", "pilates", "stretching",
        "zen", "sérénité", "calme", "repos", "repose", "ressourcement",
        # Sports loisirs calmes
        "golf", "minigolf", "piscine", "swimming pool", "plage privée", "private beach",
        "pétanque", "boules",
        # Nourriture et repos
        "déjeuner", "dîner", "pique-nique", "picnic", "thé", "café",
    ],

    "city_experience": [
        # Commerce et shopping
        "souk", "marché", "bazaar", "bazar", "boutique", "shopping",
        "achats", "commerce", "artisanat local", "souvenirs",
        # Gastronomie
        "restaurant", "gastronomie", "gastronomy", "cuisine", "food",
        "dégustation", "tasting", "street food", "couscous", "brick",
        "tajine", "brik", "harissa", "makroud", "zlabia",
        "café tunisien", "café maure", "tea", "thé à la menthe",
        # Vie urbaine
        "ville", "city", "centre-ville", "downtown", "quartier", "neighborhood",
        "médina", "avenue", "boulevard", "rue", "street",
        "marina", "port", "corniche", "front de mer", "waterfront",
        "promenade", "balade urbaine", "walking tour", "city tour",
        "visite de la ville", "city walk",
        # Loisirs urbains
        "cinéma", "cinema", "théâtre", "theater", "opéra",
        "nightlife", "vie nocturne", "bar", "pub", "discothèque",
        "rooftop", "terrasse",
        # Culturel urbain
        "street art", "graffiti", "art urbain", "murales", "mural",
        "architecture", "modernisme", "art déco",
        # Expériences locales
        "rencontre", "meeting", "visite guidée", "guided tour",
        "cours de cuisine", "cooking class", "atelier", "workshop",
    ],
}


def _normalize(text: str) -> str:
    """Minuscules + suppression des accents pour matching robuste."""
    import unicodedata
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def _build_searchable(doc: dict) -> str:
    """Concatène name + description + tags + category en texte normalisé."""
    parts = [
        doc.get("name") or "",
        doc.get("description") or "",
        " ".join(doc.get("tags") or []),
        doc.get("category") or "",
    ]
    return _normalize(" ".join(filter(None, parts)))


def infer_activity_type(doc: dict) -> Tuple[str, Dict[str, int]]:
    """
    Retourne (type_inféré, scores_par_type).
    Compte les mots-clés matchés dans le texte normalisé.
    Retourne "unknown" si aucun type ne matche.
    """
    text = _build_searchable(doc)
    scores: Dict[str, int] = {}

    for activity_type, keywords in _TYPE_RULES.items():
        normalized_kws = [_normalize(kw) for kw in keywords]
        count = sum(1 for kw in normalized_kws if kw in text)
        scores[activity_type] = count

    best_type = max(scores, key=scores.get)
    return (best_type if scores[best_type] > 0 else "unknown"), scores


def run(dry_run: bool = False) -> None:
    try:
        from app.config.mongodb import activities_collection
        col = activities_collection()
    except Exception as e:
        logger.error(f"Connexion MongoDB échouée: {e}")
        sys.exit(1)

    # Récupère tous les docs avec activity_type "unknown" ou null
    query = {"$or": [{"activity_type": "unknown"}, {"activity_type": None}, {"activity_type": {"$exists": False}}]}
    docs = list(col.find(query, {
        "name": 1, "description": 1, "tags": 1, "category": 1,
        "destination": 1, "activity_type": 1,
    }))

    logger.info(f"Docs à traiter : {len(docs)}")

    type_distribution: Dict[str, int] = {t: 0 for t in _TYPE_RULES}
    type_distribution["unknown"] = 0

    ops: List[UpdateOne] = []
    still_unknown = 0

    for doc in docs:
        inferred, scores = infer_activity_type(doc)

        if inferred != "unknown":
            type_distribution[inferred] = type_distribution.get(inferred, 0) + 1
            if not dry_run:
                ops.append(UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"activity_type": inferred}},
                ))
            else:
                top_kws = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:2]
                logger.debug(
                    f"  [{inferred}] {doc.get('name', '')[:50]}"
                    f" | scores={top_kws}"
                )
        else:
            still_unknown += 1
            type_distribution["unknown"] = type_distribution.get("unknown", 0) + 1

    logger.info("\n=== Distribution des types inférés ===")
    for t, count in sorted(type_distribution.items(), key=lambda x: -x[1]):
        logger.info(f"  {t:<20} : {count}")
    logger.info(f"\n  Total à corriger  : {len(docs) - still_unknown}")
    logger.info(f"  Restent unknown   : {still_unknown}")

    if dry_run:
        logger.info("\n[DRY RUN] Aucune écriture MongoDB — relancer sans --dry-run pour appliquer.")
        return

    if not ops:
        logger.info("Aucune mise à jour nécessaire.")
        return

    # Écriture par lots de 500
    BATCH = 500
    total_modified = 0
    for i in range(0, len(ops), BATCH):
        batch = ops[i:i + BATCH]
        result = col.bulk_write(batch, ordered=False)
        total_modified += result.modified_count
        logger.info(f"  Lot {i//BATCH + 1} : {result.modified_count} mis à jour")

    logger.info(f"\n✅ Terminé — {total_modified} / {len(docs)} documents mis à jour")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrichissement activity_type unknown → MongoDB")
    parser.add_argument("--dry-run", action="store_true", help="Simuler sans écrire")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
