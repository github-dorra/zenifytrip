"""
Import activities from app/data/fixtures/raw/*.json into MongoDB activities_collection.
Adapts fixture format to the same schema as TripAdvisor-scraped documents.
Uses upsert on (name, destination_id) to avoid duplicates.
"""

import os
import json
import pathlib
from datetime import datetime, timezone

import pymongo
from pymongo import UpdateOne
from dotenv import load_dotenv

load_dotenv()

# ─── MongoDB ──────────────────────────────────────────────────────────────────
client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
col = client["zenifytrip_db"]["activities_collection"]

# ─── Mappings ─────────────────────────────────────────────────────────────────
# le_kef fixture → kef in DB
DESTINATION_ID_MAP = {
    "le_kef": "kef",
}

PLACE_TYPE_TO_CATEGORY = {
    "Historic Sites": "Sites historiques",
    "Ancient Ruins": "Ruines anciennes",
    "Speciality Museums": "Musées spécialisés",
    "History Museums": "Musées d'histoire",
    "Religious Sites": "Sites religieux",
    "Points of Interest & Landmarks": "Monuments et points d'intérêt",
    "Art Galleries": "Galeries d'art",
    "Beaches": "Plages",
    "Parks": "Parcs",
    "National Parks": "Parcs nationaux",
    "Natural & Wildlife Areas": "Espaces naturels et sauvages",
    "Deserts": "Déserts",
    "Cultural Events": "Événements culturels",
    "Cultural Tours": "Visites culturelles",
    "Nature & Wildlife Tours": "Nature et faune",
    "4WD, ATV & Off-Road Tours": "Excursions tout terrain, 4 × 4 & VTT",
    "Equestrian Trails": "Randonnées équestres",
    "Water Parks": "Parcs aquatiques",
    "Amusement Parks": "Parcs d'attractions",
    "Spas": "Spas",
    "Flea & Street Markets": "Marchés aux puces et marchés de rue",
    "Speciality & Gift Shops": "Boutiques de souvenirs & Magasins spécialisés",
    "Specialty Shops": "Boutiques spécialisées",
    "Water Sports": "Sports nautiques",
    "Scuba & Snorkeling": "Plongée et snorkeling",
    "Boat Tours": "Excursions en bateau",
    "Bars & Clubs": "Bars et clubs",
    "Restaurants": "Restaurants",
    "Coffee & Tea": "Cafés",
    "Marinas": "Marinas",
    "Scenic Walking Areas": "Promenades pittoresques",
    "Bodies of Water": "Plans d'eau",
    "Caverns & Caves": "Grottes et cavernes",
    "Geologic Formations": "Formations géologiques",
    "Hiking Trails": "Randonnées",
    "Lookouts": "Belvédères",
    "Mountains": "Montagnes",
    "Forests": "Forêts",
    "Zoos & Aquariums": "Zoos et aquariums",
    "Neighbourhoods": "Quartiers",
    "Shopping Malls": "Centres commerciaux",
    "Cinemas": "Salles de cinéma",
    "Theatres & Performances": "Théâtres et spectacles",
    "Concerts & Shows": "Concerts et spectacles",
}

ACTIVITY_TYPE_TAGS = {
    "culture": ["culture", "historique", "patrimoine", "architecture"],
    "nature": ["nature", "plein-air", "paysage", "parc"],
    "adventure": ["aventure", "sport", "activite", "plein-air"],
    "relax": ["relaxation", "detente", "wellness", "plage"],
    "city_experience": ["ville", "gastronomie", "shopping", "urban"],
}

ACTIVITY_TYPE_TRAVELER = {
    "culture": ["culture", "histoire", "famille"],
    "nature": ["nature", "aventure", "famille"],
    "adventure": ["aventure", "sport", "jeunes"],
    "relax": ["couple", "famille", "solo"],
    "city_experience": ["famille", "solo", "couple"],
}


def map_category(place_type: str) -> str:
    if not place_type:
        return "Attractions"
    # handle composite like "Historic Sites" or "Points of Interest & Landmarks"
    for key, val in PLACE_TYPE_TO_CATEGORY.items():
        if key.lower() in place_type.lower():
            return val
    return place_type


def extract_rank(activity_id: str) -> int:
    """sidi_bou_said_3 → 3"""
    try:
        return int(activity_id.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return 999


def fixture_to_mongo(activity: dict, city_name: str, destination_id: str) -> dict:
    activity_type = activity.get("activity_type", "city_experience")
    place_type = activity.get("place_type", "")
    now = datetime.now(timezone.utc)

    return {
        "name": activity.get("name") or "",
        "name_fr": activity.get("name_fr"),
        "name_ar": activity.get("name_ar"),
        "destination": city_name,
        "destination_id": destination_id,
        "country": "Tunisie",
        "category": map_category(place_type),
        "type": "attraction",
        "rank": extract_rank(activity.get("id", "")),
        "rating": activity.get("tripadvisor_rating"),
        "reviews_count": activity.get("tripadvisor_reviews"),
        "description": None,
        "price_from_eur": None,
        "price_level": None,
        "lat": activity.get("lat"),
        "lng": activity.get("lng"),
        "tags": ACTIVITY_TYPE_TAGS.get(activity_type, ["culture"]),
        "traveler_types": ACTIVITY_TYPE_TRAVELER.get(activity_type, ["famille"]),
        "is_core_tag": activity.get("is_core_tag", False),
        "business_score": activity.get("business_score", 0.2),
        "activity_type": activity_type,
        "source": activity.get("source", "tripadvisor"),
        "has_geospatial_info": activity.get("has_geospatial_info", False),
        "scraped_at": now,
        "last_updated": now,
    }


def import_fixtures():
    fixture_dir = pathlib.Path("app/data/fixtures/raw")
    total_upserted = 0
    total_modified = 0
    total_skipped = 0
    city_results = []

    for fixture_file in sorted(fixture_dir.glob("*.json")):
        with open(fixture_file, encoding="utf-8") as fp:
            data = json.load(fp)

        file_stem = fixture_file.stem
        destination_id = DESTINATION_ID_MAP.get(file_stem, file_stem)
        city_name = data.get("city", file_stem.replace("_", " ").title())
        activities = data.get("activities", [])

        if not activities:
            print(f"  {file_stem}: 0 activities in fixture — skipped")
            continue

        ops = []
        for act in activities:
            name = act.get("name", "").strip()
            if not name:
                continue
            doc = fixture_to_mongo(act, city_name, destination_id)
            ops.append(UpdateOne(
                {"name": name, "destination_id": destination_id},
                {"$setOnInsert": doc},
                upsert=True,
            ))

        if not ops:
            continue

        result = col.bulk_write(ops, ordered=False)
        upserted = result.upserted_count
        modified = result.modified_count
        skipped = len(ops) - upserted - modified

        total_upserted += upserted
        total_modified += modified
        total_skipped += skipped

        city_results.append({
            "city": file_stem,
            "destination_id": destination_id,
            "total_in_fixture": len(activities),
            "new_inserted": upserted,
            "already_existed": skipped,
        })
        print(f"  {file_stem} ({destination_id}): {upserted} new | {skipped} already in DB")

    print()
    print(f"TOTAL: {total_upserted} new inserted | {total_skipped} already existed")
    return city_results


if __name__ == "__main__":
    print("Importing fixtures into MongoDB activities_collection...")
    print()
    import_fixtures()
    print()
    # Final count
    pipeline = [
        {"$group": {"_id": "$destination_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    total = col.count_documents({})
    print(f"TOTAL documents in collection: {total}")
    for r in col.aggregate(pipeline):
        print(f"  {r['_id']}: {r['count']}")
