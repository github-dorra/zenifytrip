"""
Migration : normaliser les anciens documents TripAdvisor dans restaurant_collection.

Problème : deux schémas coexistants dans la même collection :
  - TripAdvisor  (~1200 docs) : "cuisines", pas de "zone", pas de "geo"
  - RestaurantGuru (~2284 docs) : "categories", "zone", "geo"

Actions :
  1. Ajouter "categories" = valeur de "cuisines" sur les docs TripAdvisor
  2. Ajouter "zone" = "Gouvernorat de {city}" sur les docs TripAdvisor (approximation)
  3. Supprimer ancien index name_1_destination_id_1 si présent
  4. Créer les bons index (name+city unique, city, zone, rating, source)

Usage :
  python -m app.scripts.migrate_restaurants_schema
"""

import os
import sys
import logging
from pymongo import MongoClient, IndexModel, ASCENDING, DESCENDING
from dotenv import load_dotenv

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
load_dotenv(dotenv_path=os.path.join(ROOT, ".env"))

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "zenifytrip_db")
COLLECTION  = "restaurant_collection"

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

# Mapping ville → gouvernorat pour les docs TripAdvisor qui n'ont pas de "zone"
CITY_TO_ZONE = {
    "Tunis":    "Gouvernorat de Tunis",
    "Sousse":   "Gouvernorat de Sousse",
    "Djerba":   "Gouvernorat de Médenine",
    "Hammamet": "Gouvernorat de Nabeul",
    "Nabeul":   "Gouvernorat de Nabeul",
    "Monastir": "Gouvernorat de Monastir",
    "Kairouan": "Gouvernorat de Kairouan",
    "Tozeur":   "Gouvernorat de Tozeur",
    "Sfax":     "Gouvernorat de Sfax",
    "Bizerte":  "Gouvernorat de Bizerte",
    "Gabès":    "Gouvernorat de Gabès",
    "Gafsa":    "Gouvernorat de Gafsa",
}


def run():
    if not MONGODB_URI:
        log.error("MONGODB_URI manquant dans .env")
        sys.exit(1)

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    col = client[MONGODB_DB][COLLECTION]

    total = col.count_documents({})
    ta    = col.count_documents({"source": "tripadvisor"})
    guru  = col.count_documents({"source": "restaurantguru"})
    log.info(f"Collection : {total} docs total  |  {ta} TripAdvisor  |  {guru} RestaurantGuru")

    # ── 1. Supprimer ancien index conflictuel ─────────────────────────────────
    try:
        existing = col.index_information()
        if "name_1_destination_id_1" in existing:
            col.drop_index("name_1_destination_id_1")
            log.info("Index supprimé : name_1_destination_id_1")
        else:
            log.info("Index name_1_destination_id_1 déjà absent — OK")
    except Exception as e:
        log.warning(f"Impossible de supprimer l'index : {e}")

    # ── 2. Ajouter "categories" sur les docs TripAdvisor qui n'en ont pas ─────
    # Utilise un pipeline d'agrégation MongoDB 4.2+ pour copier cuisines → categories
    result = col.update_many(
        {
            "source":     "tripadvisor",
            "categories": {"$exists": False},
            "cuisines":   {"$exists": True},
        },
        [{"$set": {"categories": "$cuisines"}}]
    )
    log.info(f"categories ajouté : {result.modified_count} docs TripAdvisor mis à jour")

    # ── 3. Ajouter "zone" sur les docs TripAdvisor qui n'en ont pas ──────────
    zone_total = 0
    for city, zone in CITY_TO_ZONE.items():
        r = col.update_many(
            {
                "source": "tripadvisor",
                "city":   city,
                "zone":   {"$exists": False},
            },
            {"$set": {"zone": zone}}
        )
        if r.modified_count:
            log.info(f"  zone ajouté : {city:12s} → {zone}  ({r.modified_count} docs)")
            zone_total += r.modified_count

    # Fallback pour villes sans mapping : zone = city
    r = col.update_many(
        {
            "source": "tripadvisor",
            "zone":   {"$exists": False},
        },
        [{"$set": {"zone": "$city"}}]
    )
    if r.modified_count:
        log.info(f"  zone = city (fallback) : {r.modified_count} docs")
        zone_total += r.modified_count

    log.info(f"zone ajouté total : {zone_total} docs TripAdvisor")

    # ── 4. Recréer les index corrects ─────────────────────────────────────────
    try:
        # Supprimer d'éventuels index obsolètes par nom
        for idx_name in ["name_1_city_slug_1", "destination_id_1", "cuisines_1"]:
            if idx_name in col.index_information():
                col.drop_index(idx_name)
                log.info(f"Index obsolète supprimé : {idx_name}")
    except Exception as e:
        log.warning(f"Nettoyage index : {e}")

    col.create_indexes([
        IndexModel([("name", ASCENDING), ("city", ASCENDING)], unique=True),
        IndexModel([("city",        ASCENDING)]),
        IndexModel([("zone",        ASCENDING)]),
        IndexModel([("rating",      DESCENDING)]),
        IndexModel([("price_level", ASCENDING)]),
        IndexModel([("source",      ASCENDING)]),
        IndexModel([("categories",  ASCENDING)]),
    ])
    log.info("Index recréés : name+city (unique), city, zone, rating, price_level, source, categories")

    # ── 5. Vérification finale ────────────────────────────────────────────────
    missing_categories = col.count_documents({"categories": {"$exists": False}})
    missing_zone       = col.count_documents({"zone":       {"$exists": False}})
    log.info(f"Vérification : docs sans 'categories' = {missing_categories}  |  sans 'zone' = {missing_zone}")

    total_after = col.count_documents({})
    log.info(f"Migration terminée — {total_after} docs dans la collection")
    client.close()


if __name__ == "__main__":
    run()
