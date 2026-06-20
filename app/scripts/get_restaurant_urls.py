"""Output all restaurant tripadvisor_url + restaurant_id + name + city as JSON"""
import json, os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
client = MongoClient(os.getenv("MONGODB_URI"))
col = client["zenifytrip_db"]["restaurant_collection"]

docs = list(col.find({}, {"_id": 0, "name": 1, "city": 1, "restaurant_id": 1, "tripadvisor_url": 1}))
docs = [d for d in docs if d.get("tripadvisor_url")]

print(json.dumps(docs))
client.close()
