"""
Consolide les 8 fichiers JSON restaurants (Downloads) et upload vers MongoDB Atlas
Collection : restaurant_collection
"""
import json
import os
import glob
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
load_dotenv(dotenv_path=os.path.join(ROOT, ".env"))

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "zenifytrip_db")
COLLECTION  = "restaurant_collection"
DOWNLOADS   = os.path.expanduser("~/Downloads")

def main():
    pattern = os.path.join(DOWNLOADS, "restaurants_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"Aucun fichier trouvé dans {DOWNLOADS}")
        return

    print(f"\n{'='*60}")
    print(f"TripAdvisor -> MongoDB  ({MONGODB_DB}.{COLLECTION})")
    print(f"{'='*60}\n")

    all_restaurants = []
    now = datetime.now(timezone.utc).isoformat()

    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        for r in data:
            r["scraped_at"] = now
        city = data[0]["city"] if data else os.path.basename(f)
        print(f"  {city:12s}  {len(data)} restaurants  <- {os.path.basename(f)}")
        all_restaurants.extend(data)

    print(f"\nTotal consolide : {len(all_restaurants)} restaurants")
    print("Upload vers MongoDB Atlas...\n")

    client = MongoClient(MONGODB_URI)
    col = client[MONGODB_DB][COLLECTION]

    col.create_index([("name", 1), ("city", 1)], unique=True, background=True)
    col.create_index([("city_slug", 1)])
    col.create_index([("rating", -1)])
    col.create_index([("cuisines", 1)])
    col.create_index([("restaurant_id", 1)])

    ops = [
        UpdateOne(
            {"name": r["name"], "city": r["city"]},
            {"$set": r},
            upsert=True,
        )
        for r in all_restaurants
    ]

    result = col.bulk_write(ops, ordered=False)
    total = col.count_documents({})
    client.close()

    print(f"{'='*60}")
    print(f"Inseres   : {result.upserted_count}")
    print(f"Mis a jour: {result.modified_count}")
    print(f"Total collection : {total}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
