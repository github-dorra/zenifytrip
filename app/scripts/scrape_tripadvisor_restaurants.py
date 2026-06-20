"""
Scrape TripAdvisor restaurants for major Tunisian cities
and save to MongoDB Atlas → zenifytrip_db.restaurant_collection
"""
import re
import time
import os
import sys

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

# ── env ──────────────────────────────────────────────────────────────────────
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
load_dotenv(dotenv_path=os.path.join(ROOT, ".env"))

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "zenifytrip_db")
COLLECTION  = "restaurant_collection"

# ── cities ───────────────────────────────────────────────────────────────────
CITIES = [
    {"name": "Tunis",    "slug": "tunis",    "geo": "g293758", "suffix": "Tunis_Tunis_Governorate"},
    {"name": "Sousse",   "slug": "sousse",   "geo": "g295401", "suffix": "Sousse_Sousse_Governorate"},
    {"name": "Djerba",   "slug": "djerba",   "geo": "g297941", "suffix": "Djerba_Island_Medenine_Governorate"},
    {"name": "Hammamet", "slug": "hammamet", "geo": "g297943", "suffix": "Hammamet_Nabeul_Governorate"},
    {"name": "Monastir", "slug": "monastir", "geo": "g297949", "suffix": "Monastir_Monastir_Governorate"},
    {"name": "Kairouan", "slug": "kairouan", "geo": "g303925", "suffix": "Kairouan_Kairouan_Governorate"},
    {"name": "Tozeur",   "slug": "tozeur",   "geo": "g293757", "suffix": "Tozeur_Tozeur_Governorate"},
    {"name": "Nabeul",   "slug": "nabeul",   "geo": "g317086", "suffix": "Nabeul_Nabeul_Governorate"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xhtml,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── parser ────────────────────────────────────────────────────────────────────
def _parse_page(html: str, city_name: str, city_slug: str) -> list[dict]:
    """
    TripAdvisor embeds restaurant data in JSON blobs inside <script> tags.
    We try two approaches:
      1. Parse the structured JSON (pageManifest / redux state)
      2. Fall back to BeautifulSoup HTML parsing of rendered cards
    """
    restaurants = []
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # ── Approach 1: JSON state blob ────────────────────────────────────────
    # TripAdvisor SSR embeds window.__taReactApplicationManifest or similar
    json_blobs = re.findall(
        r'window\.__(?:WEB_CONTEXT|taReactApplicationManifest|redux__)?.*?=\s*(\{.*?\});',
        html, re.DOTALL
    )
    # Also try the TA JSON-LD structured data
    soup = BeautifulSoup(html, "lxml")

    # ── Approach 2: HTML card parsing ──────────────────────────────────────
    # TripAdvisor restaurant cards have a consistent text structure in the HTML
    # even before JS execution (partial SSR)
    cards = soup.select('[data-test-target="restaurants-list"] div[class]')

    # Find all Restaurant_Review links
    links = []
    for a in soup.find_all("a", href=re.compile(r"Restaurant_Review")):
        href = a.get("href", "")
        if "#" not in href and href not in links:
            links.append(href if href.startswith("http") else "https://www.tripadvisor.fr" + href)

    # Get images
    img_map: dict[str, str] = {}
    for a in soup.find_all("a", href=re.compile(r"Restaurant_Review")):
        if "#" in a.get("href", ""):
            continue
        img = a.find("img")
        if img and img.get("src"):
            key = a["href"].split("Reviews-")[-1] if "Reviews-" in a["href"] else None
            if key:
                img_map[key] = img["src"].split("?")[0]

    # Parse the full text content of the list
    list_el = soup.select_one('[data-test-target="restaurants-list"]')
    if not list_el:
        print(f"    [!] no restaurants-list found for {city_name}")
        return restaurants

    full_text = list_el.get_text("\n")
    blocks = re.split(r'\n(?=\d+\.\s)', full_text)

    for idx, block in enumerate(blocks):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines or not re.match(r'^\d+\.', lines[0]):
            continue

        rank_match = re.match(r'^(\d+)\.\s+(.+)$', lines[0])
        if not rank_match:
            continue

        rank = int(rank_match.group(1))
        name = rank_match.group(2).strip()

        rating_raw = lines[1] if len(lines) > 1 else ""
        try:
            rating = float(rating_raw.replace(",", "."))
        except ValueError:
            rating = None

        reviews_raw = lines[2] if len(lines) > 2 else ""
        reviews_match = re.search(r'\(([0-9 ]+)\s*avis\)', reviews_raw)
        reviews = int(reviews_match.group(1).replace(" ", "")) if reviews_match else None

        cuisine_raw = lines[3] if len(lines) > 3 else ""
        cuisines = [c.strip() for c in cuisine_raw.split(",") if c.strip() and "€" not in c]

        price_raw = lines[4] if len(lines) > 4 else ""
        price = price_raw.strip() if re.match(r'^€', price_raw) else None

        status_raw = lines[5] if len(lines) > 5 else ""
        if "fermé" in status_raw.lower():
            status = "Fermé"
        elif "ouv" in status_raw.lower():
            status = status_raw.strip()
        else:
            status = None

        url = links[idx - 1] if idx - 1 < len(links) else None
        url_key = url.split("Reviews-")[-1] if url and "Reviews-" in url else None
        photo = img_map.get(url_key) if url_key else None

        restaurants.append({
            "rank":           rank,
            "name":           name,
            "rating":         rating,
            "reviews":        reviews,
            "cuisines":       cuisines,
            "price_level":    price,
            "status":         status,
            "city":           city_name,
            "city_slug":      city_slug,
            "tripadvisor_url": url,
            "photo_url":      photo,
            "source":         "tripadvisor",
            "scraped_at":     now,
        })

    return restaurants


# ── fetch + parse ─────────────────────────────────────────────────────────────
def fetch_city(city: dict) -> list[dict]:
    url = (
        f"https://www.tripadvisor.fr/Restaurants-{city['geo']}"
        f"-{city['suffix']}.html"
    )
    print(f"  Fetching {city['name']:12s}  {url}")
    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
        return _parse_page(resp.text, city["name"], city["slug"])
    except Exception as e:
        print(f"    [ERR] {e}")
        return []


# ── MongoDB ───────────────────────────────────────────────────────────────────
def save_to_mongo(restaurants: list[dict]) -> tuple[int, int]:
    if not restaurants:
        return 0, 0
    client = MongoClient(MONGODB_URI)
    col = client[MONGODB_DB][COLLECTION]

    col.create_index([("name", 1), ("city", 1)], unique=True, background=True)
    col.create_index([("city_slug", 1)])
    col.create_index([("rating", -1)])
    col.create_index([("cuisines", 1)])

    ops = [
        UpdateOne(
            {"name": r["name"], "city": r["city"]},
            {"$set": r},
            upsert=True,
        )
        for r in restaurants
    ]
    result = col.bulk_write(ops, ordered=False)
    total = col.count_documents({})
    client.close()
    return result.upserted_count, result.modified_count, total


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"TripAdvisor -> MongoDB  ({MONGODB_DB}.{COLLECTION})")
    print(f"{'='*60}\n")

    all_restaurants: list[dict] = []

    for city in CITIES:
        data = fetch_city(city)
        print(f"    => {len(data)} restaurants extracted")
        all_restaurants.extend(data)
        time.sleep(1.5)  # polite delay between requests

    print(f"\nTotal extraits : {len(all_restaurants)}")
    print("Sauvegarde dans MongoDB Atlas...")

    inserted, updated, total = save_to_mongo(all_restaurants)
    print(f"\n{'='*60}")
    print(f"Insérés  : {inserted}")
    print(f"Mis à jour: {updated}")
    print(f"Total collection : {total}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
