"""
Migration one-shot : monastir_activities_tripadvisor.json → MongoDB Atlas
Usage : python -m app.scripts.migrate_fixtures_to_mongo
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from app.config.mongodb import activities_collection

FIXTURE = Path(__file__).parent.parent / "data" / "fixtures" / "monastir_activities_tripadvisor.json"

NOW = datetime.now(timezone.utc)


def _enrich(doc: dict, destination: str, dest_id: str, doc_type: str) -> dict:
    doc.setdefault("destination_id", dest_id)
    doc.setdefault("destination", destination)
    doc.setdefault("country", "Tunisie")
    doc.setdefault("type", doc_type)
    doc.setdefault("source", "tripadvisor")
    doc.setdefault("scraped_at", NOW)
    doc.setdefault("last_updated", NOW)
    return doc


def _upsert(col, docs: list[dict]) -> tuple[int, int]:
    if not docs:
        return 0, 0
    ops = [
        UpdateOne(
            {"name": d["name"], "destination_id": d["destination_id"]},
            {"$set": d},
            upsert=True,
        )
        for d in docs
    ]
    try:
        r = col.bulk_write(ops, ordered=False)
        return r.upserted_count, r.modified_count
    except BulkWriteError as e:
        print(f"  BulkWriteError : {e.details}")
        return 0, 0


def run():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    destination = data.get("destination", "Monastir")
    dest_id     = destination.lower()

    print(f"Migration fixture -> destination : {destination}")

    attractions = [_enrich(d, destination, dest_id, "attraction")
                   for d in data.get("attractions", [])]
    tours       = [_enrich(d, destination, dest_id, "tour")
                   for d in data.get("tours_and_experiences", [])]
    restaurants = [_enrich(d, destination, dest_id, "restaurant")
                   for d in data.get("restaurants", [])]

    col = activities_collection()
    a_up, a_mod = _upsert(col, attractions)
    t_up, t_mod = _upsert(col, tours)
    r_up, r_mod = _upsert(col, restaurants)

    total_up  = a_up  + t_up  + r_up
    total_mod = a_mod + t_mod + r_mod
    print(f"  attractions : {a_up} insérés, {a_mod} mis à jour ({len(attractions)} total)")
    print(f"  tours       : {t_up} insérés, {t_mod} mis à jour ({len(tours)} total)")
    print(f"  restaurants : {r_up} insérés, {r_mod} mis à jour ({len(restaurants)} total)")
    print(f"  TOTAL : {total_up} inseres, {total_mod} mis a jour -> collection 'activities_collection'")
    print("Migration terminée.")


if __name__ == "__main__":
    run()
