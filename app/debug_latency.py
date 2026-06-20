import time
import requests
from app.config.settings import GOOGLE_MAPS_API_KEY
from app.services.cache_service import cache

PLACES_API_BASE = "https://maps.googleapis.com/maps/api"

print("=== DIAGNOSTIC LATENCE ===\n")

# 1. Test HTTP brut — Google Places Text Search
print("1. Test HTTP brut (Google Places Text Search)...")
url = f"{PLACES_API_BASE}/place/textsearch/json"
params = {
    "query": "restaurant sousse tunisie",
    "type":  "restaurant",
    "key":   GOOGLE_MAPS_API_KEY,
}
t0 = time.time()
try:
    resp = requests.get(url, params=params, timeout=10)
    elapsed = int((time.time() - t0) * 1000)
    results = resp.json().get("results", [])
    print(f"   HTTP status={resp.status_code} | {len(results)} résultats | {elapsed}ms")
except Exception as e:
    elapsed = int((time.time() - t0) * 1000)
    print(f"   ERREUR ({elapsed}ms): {e}")

# 2. Test HTTP brut — Google Places Details
print("\n2. Test HTTP brut (Place Details)...")
if results:
    place_id = results[0].get("place_id", "")
    url2 = f"{PLACES_API_BASE}/place/details/json"
    params2 = {
        "place_id": place_id,
        "fields":   "formatted_phone_number,website,opening_hours,dine_in,takeout",
        "key":      GOOGLE_MAPS_API_KEY,
    }
    t0 = time.time()
    try:
        resp2 = requests.get(url2, params=params2, timeout=10)
        elapsed2 = int((time.time() - t0) * 1000)
        print(f"   HTTP status={resp2.status_code} | {elapsed2}ms")
    except Exception as e:
        elapsed2 = int((time.time() - t0) * 1000)
        print(f"   ERREUR ({elapsed2}ms): {e}")

# 3. Test cache.set() — écriture fichier
print("\n3. Test cache.set() (écriture async)...")
t0 = time.time()
cache.set("test_latency_key", {"data": "test"}, 60)
elapsed3 = int((time.time() - t0) * 1000)
print(f"   cache.set() retour en {elapsed3}ms (async — écriture en arrière-plan)")

# 4. Vérifier taille du fichier cache
import os
cache_file = "app/.cache/zenifytrip_cache.json"
if os.path.exists(cache_file):
    size_kb = os.path.getsize(cache_file) / 1024
    print(f"\n4. Taille fichier cache: {size_kb:.1f} KB")
    print(f"   Nb entrées en mémoire: {len(cache._store)}")
else:
    print("\n4. Fichier cache introuvable")

print("\n=== FIN DIAGNOSTIC ===")
