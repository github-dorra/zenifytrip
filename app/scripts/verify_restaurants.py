import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
client = MongoClient(os.getenv("MONGODB_URI"))
col = client["zenifytrip_db"]["restaurant_collection"]

total = col.count_documents({})
print(f"Total documents in restaurant_collection: {total}\n")

pipeline = [
    {"$group": {"_id": "$city", "count": {"$sum": 1}, "avg_rating": {"$avg": "$rating"}}},
    {"$sort": {"count": -1}}
]
by_city = list(col.aggregate(pipeline))
for c in by_city:
    avg = c["avg_rating"] or 0
    print(f"  {c['_id']:12s} : {c['count']:3d} restaurants  (avg rating: {avg:.2f})")

print("\nSample document (rank 1 Tunis):")
sample = col.find_one({"city": "Tunis", "rank": 1})
if sample:
    sample.pop("_id", None)
    import json
    print(json.dumps(sample, ensure_ascii=False, indent=2))

client.close()
