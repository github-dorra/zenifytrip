"""
create_restaurant_search_index.py
Crée (ou met à jour) l'index Atlas Search de production sur
restaurant_collection — remplace le filtrage par expressions régulières
de mongo_restaurant_service.py par une recherche plein texte native.

Faisabilité validée le 2026-07-23 (index de test "restaurant_search_test").
Ce script crée l'index sous un nom stable ("restaurant_search") réutilisé
par le code applicatif — idempotent, peut être relancé sans risque.

Usage:
  venv1\\Scripts\\python app\\scripts\\create_restaurant_search_index.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import pymongo
from app.config.settings import MONGODB_URI, MONGODB_DB

INDEX_NAME = "restaurant_search"

DEFINITION = {
    "mappings": {
        "dynamic": False,
        "fields": {
            "name":                {"type": "string"},
            "categories":          {"type": "string"},
            "tags":                {"type": "string"},
            "description":         {"type": "string"},
            "city":                {"type": "string"},
            "zone":                {"type": "string"},
            "address":             {"type": "string"},
            "features":            {"type": "string"},
            "establishment_types": {"type": "string"},
        }
    }
}


def main():
    client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    db = client[MONGODB_DB]
    col = db["restaurant_collection"]

    existing = list(col.aggregate([{"$listSearchIndexes": {}}]))
    names = {idx.get("name") for idx in existing}

    if INDEX_NAME in names:
        print(f"Index '{INDEX_NAME}' existe déjà — mise à jour de la définition.")
        db.command({
            "updateSearchIndex": "restaurant_collection",
            "name": INDEX_NAME,
            "definition": DEFINITION,
        })
    else:
        print(f"Création de l'index '{INDEX_NAME}'...")
        db.command({
            "createSearchIndexes": "restaurant_collection",
            "indexes": [{"name": INDEX_NAME, "definition": DEFINITION}],
        })

    # Attente READY
    for _ in range(20):
        indexes = list(col.aggregate([{"$listSearchIndexes": {}}]))
        idx = next((i for i in indexes if i.get("name") == INDEX_NAME), None)
        if idx and idx.get("status") == "READY" and idx.get("queryable"):
            print(f"Index '{INDEX_NAME}' READY et interrogeable.")
            return
        time.sleep(5)

    print(f"ATTENTION : index '{INDEX_NAME}' pas encore READY après 100s — vérifier manuellement.")


if __name__ == "__main__":
    main()
