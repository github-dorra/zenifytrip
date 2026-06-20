"""
Mini HTTP server — reçoit les données restaurants du browser via POST
et les insère dans MongoDB Atlas restaurant_collection.
Usage: python tripadvisor_receiver.py
       Puis le browser poste les données via fetch().
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "zenifytrip_db")
COLLECTION  = "restaurant_collection"
PORT        = 8765

client     = MongoClient(MONGODB_URI)
db         = client[MONGODB_DB]
collection = db[COLLECTION]

total_inserted  = 0
total_updated   = 0
cities_received = []


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silence default access log

    def do_OPTIONS(self):
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == "/restaurants":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
                self._upsert(payload)
                self._cors()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif self.path == "/done":
            self._cors()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            print(f"\n--- Scraping terminé ---")
            print(f"Villes : {cities_received}")
            print(f"Insérés : {total_inserted}  |  Mis à jour : {total_updated}")
            print(f"Total collection : {collection.count_documents({})}")
            sys.exit(0)

        else:
            self.send_response(404)
            self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def _upsert(self, restaurants: list):
        global total_inserted, total_updated
        if not restaurants:
            return

        city = restaurants[0].get("city", "?")
        cities_received.append(city)

        ops = []
        for r in restaurants:
            # clé d'unicité : nom + ville
            key = {"name": r["name"], "city": r["city"]}
            r["updated_at"] = datetime.now(timezone.utc).isoformat()
            ops.append(UpdateOne(key, {"$set": r}, upsert=True))

        result = collection.bulk_write(ops, ordered=False)
        ins = result.upserted_count
        upd = result.modified_count
        total_inserted += ins
        total_updated  += upd
        print(f"  [{city:12s}]  {len(restaurants):2d} restaurants  →  "
              f"{ins} insérés, {upd} mis à jour")


if __name__ == "__main__":
    # Création index unicité
    collection.create_index([("name", 1), ("city", 1)], unique=True, background=True)
    collection.create_index([("city_slug", 1)])
    collection.create_index([("rating", -1)])
    collection.create_index([("cuisines", 1)])

    print(f"Serveur démarré sur http://localhost:{PORT}")
    print(f"DB : {MONGODB_DB} / collection : {COLLECTION}")
    print("En attente des données du browser...\n")

    server = HTTPServer(("localhost", PORT), Handler)
    server.serve_forever()
