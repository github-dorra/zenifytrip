#!/usr/bin/env python3
"""
fetch_restaurant_from_guru.py
Scrape all restaurants from fr.restaurantguru.com for Tunisian cities
and upsert into MongoDB restaurant_collection.

Requirements (already in venv1):
    cloudscraper beautifulsoup4 pymongo python-dotenv lxml

Run:
    venv1\\Scripts\\python app\\scripts\\fetch_restaurant_from_guru.py
"""

import json
import os
import re
import sys
import time
import logging
from pathlib import Path
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError
from dotenv import load_dotenv

# ── env ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "zenifytrip_db")
COLLECTION  = "restaurant_collection"

# ── logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── config ───────────────────────────────────────────────────────────
BASE_URL   = "https://fr.restaurantguru.com"
MAX_PAGES  = 200       # cap per city (200 × 20 = 4000 max)
BATCH_DB   = 15        # docs per MongoDB bulk_write
DELAY_LIST = 2.0       # seconds between list-page fetches
DELAY_DET  = 1.5       # seconds between detail-page fetches
RETRIES    = 3
TIMEOUT    = 30

# progress file — allows resuming after interruption
PROGRESS_FILE = ROOT / "app" / ".cache" / "restaurantguru_progress.json"

# ── city definitions ─────────────────────────────────────────────────
# Villes déjà scrapées — SKIP si already_done couvre toutes les URLs
CITIES_DONE = {
    "Tunis", "Sousse", "Djerba", "Hammamet", "Monastir", "Tozeur", "Nabeul",
    "Kairouan", "Ariana", "La Marsa", "Hammam Sousse", "Sfax",
    "Bizerte", "Mahdia", "Hammamet Sud", "Akouda", "Gafsa", "Gabes",
}

CITIES = [
    # ── Déjà scrapées (progress file couvre leurs URLs) ───────────────
    {"name": "Tunis",          "slugs": ["Tunis"]},
    {"name": "Sousse",         "slugs": ["Sousse"]},
    {"name": "Djerba",         "slugs": ["Houmt-Souk"]},
    {"name": "Hammamet",       "slugs": ["Hammamet"]},
    {"name": "Monastir",       "slugs": ["Monastir"]},
    {"name": "Tozeur",         "slugs": ["Tozeur"]},
    {"name": "Nabeul",         "slugs": ["Nabeul"]},
    {"name": "Kairouan",       "slugs": ["Al-Qayrawan"]},
    {"name": "Ariana",         "slugs": ["Ariana"]},
    {"name": "La Marsa",       "slugs": ["La-Marsa"]},
    {"name": "Hammam Sousse",  "slugs": ["Hammam-Sousse"]},
    {"name": "Sfax",           "slugs": ["Sfax"]},
    {"name": "Bizerte",        "slugs": ["Bizerte"]},
    {"name": "Mahdia",         "slugs": ["Mahdia"]},
    {"name": "Djerba Midun",   "slugs": ["Djerba-Midun"]},             # 303 — slug corrigé
    {"name": "Hammamet Sud",   "slugs": ["Hammamet-Sud"]},
    {"name": "Akouda",         "slugs": ["Akouda"]},
    {"name": "Gafsa",          "slugs": ["Gafsa"]},
    {"name": "Gabes",          "slugs": ["Gabes"]},
    # ── Nouvelles villes ──────────────────────────────────────────────
    {"name": "El Mourouj",     "slugs": ["El-Mourouj"]},               # 428
    {"name": "Ben Arous",      "slugs": ["Ben-Arous"]},                # 426
    {"name": "Ez Zahra",       "slugs": ["Ez-Zahra"]},                 # 241
    {"name": "Hammam Lif",     "slugs": ["Hammam-Lif"]},               # 258
    {"name": "Médenine",       "slugs": ["Medinine"]},                 # 237
    {"name": "Le Kef",         "slugs": ["El-Kef"]},                   # 229
    {"name": "Zarzis",         "slugs": ["Zarzis"]},                   # 229
    {"name": "Rades",          "slugs": ["Rades"]},                    # 226
    {"name": "Tataouine",      "slugs": ["Tataouine"]},                # 226
    {"name": "Yasmine Hammamet","slugs": ["Yasmine-Hammamet"]},        # 204
    {"name": "Cebalat",        "slugs": ["Cebalat"]},                  # 197
    {"name": "Jendouba",       "slugs": ["Jendouba"]},                 # 182
    {"name": "Zaghouan",       "slugs": ["Zaghouan"]},                 # 174
    {"name": "Sidi Bouzid",    "slugs": ["Sidi-Bouzid"]},             # 175
    {"name": "Kasserine",      "slugs": ["Kasserine"]},                # 175
    {"name": "Fouchana",       "slugs": ["Fouchana"]},                 # 173
    {"name": "La Goulette",    "slugs": ["La-Goulette"]},              # 369
    {"name": "Manouba",        "slugs": ["Manouba"]},                  # 310
    {"name": "Kelibia",        "slugs": ["Kelibia"]},                  # 307
    {"name": "Ksar Hellal",    "slugs": ["Ksar-Hellal"]},             # 157
    {"name": "Tabarka",        "slugs": ["Tabarka"]},                  # 147
    {"name": "Grombalia",      "slugs": ["Grombalia"]},                # 138
    {"name": "El Manara",      "slugs": ["El-Manara"]},               # 133
    {"name": "Korba",          "slugs": ["Korba-Nabeul"]},            # 124
    {"name": "Gammarth",       "slugs": ["Gammarth"]},                 # 117
    {"name": "Oued Ellil",     "slugs": ["Oued-Ellil"]},              # 113
    {"name": "Rafraf",         "slugs": ["Raf-Raf"]},                  # 111
    {"name": "Ben Gardane",    "slugs": ["Ben-Gardane"]},              # 111
    {"name": "Douz",           "slugs": ["Douz"]},                     # 110
]

# sub-paths that are NOT the restaurant main page
SKIP_PATHS = {"/reviews", "/menu", "/photos", "/map", "/reservations", "/order"}

# slugs that are city names, filters, or pagination markers
SKIP_SLUGS = {
    "Tunis","Sousse","Djerba","Hammamet","Monastir","Kairouan","Tozeur","Nabeul",
    "Al-Qayrawan","Ariana","La-Marsa","Hammam-Sousse","Sfax","Bizerte","Mahdia",
    "Djerba-Midun","Hammamet-Sud","Akouda","Gafsa","Gabes",
    "El-Mourouj","Ben-Arous","Ez-Zahra","Hammam-Lif","Medinine","El-Kef","Zarzis",
    "Rades","Tataouine","Yasmine-Hammamet","Cebalat","Jendouba","Zaghouan",
    "Sidi-Bouzid","Kasserine","Fouchana","La-Goulette","Manouba","Kelibia",
    "Ksar-Hellal","Tabarka","Grombalia","El-Manara","Korba-Nabeul","Gammarth",
    "Oued-Ellil","Raf-Raf","Ben-Gardane","Douz",
    "Tunisia","Djerba-Island","Houmt-Souk","Houmt-Souk-Djerba",
    "Beja","Kef","Siliana","restaurant","restaurants","top",
    "seafood","pizza","delivery","takeaway","cafe","fast-food",
    "reviews","menu","photos","map","reservations","order",
}

# ── cloudscraper session (bypasses Cloudflare / bot detection) ────────
_scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)


# ══════════════════════════════════════════════════════════════════════
#  HTTP helpers
# ══════════════════════════════════════════════════════════════════════

def fetch(url: str, delay: float = 0) -> Optional[str]:
    if delay:
        time.sleep(delay)
    for attempt in range(1, RETRIES + 1):
        try:
            r = _scraper.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                wait = 20 * attempt
                log.warning(f"429 rate-limit — waiting {wait}s")
                time.sleep(wait)
            else:
                log.warning(f"HTTP {r.status_code}: {url}")
                time.sleep(5)
        except Exception as exc:
            log.warning(f"Attempt {attempt}/{RETRIES} failed: {exc}")
            time.sleep(6)
    log.error(f"All {RETRIES} attempts failed: {url}")
    return None


# ══════════════════════════════════════════════════════════════════════
#  List-page parsing — collect restaurant URLs
# ══════════════════════════════════════════════════════════════════════

def _is_restaurant_url(href: str) -> bool:
    """True only if href is a restaurant main-page URL."""
    if not href or "restaurantguru.com" not in href:
        return False

    # strip query string and trailing slash
    clean = href.split("?")[0].rstrip("/")

    # skip sub-pages (reviews, menu, photos …)
    path_part = clean.replace(BASE_URL, "")
    for sp in SKIP_PATHS:
        if path_part.endswith(sp) or f"{sp}/" in path_part:
            return False

    slug = clean.split("/")[-1]
    if len(slug) < 5:
        return False
    if slug in SKIP_SLUGS:
        return False
    if slug.isdigit():
        return False

    return True


def extract_urls_from_page(html: str) -> list[str]:
    """Return unique restaurant URLs from one listing page."""
    soup = BeautifulSoup(html, "lxml")

    # #restaurant-list is the confirmed main container
    container = soup.select_one("#restaurant-list") or soup.body

    urls: list[str] = []
    seen: set[str] = set()

    for a in container.select("a[href]"):
        raw = a.get("href", "").split("?")[0].strip()
        if raw.startswith("/"):
            raw = BASE_URL + raw
        if not raw.startswith("http"):
            continue
        href = raw.rstrip("/")
        if href in seen:
            continue
        if _is_restaurant_url(href):
            seen.add(href)
            urls.append(href)

    return urls


def collect_city_urls(city: dict) -> list[str]:
    """Try each slug variant; paginate until no new URLs or MAX_PAGES."""
    city_name    = city["name"]
    all_urls: list[str] = []
    seen: set[str] = set()
    working_slug: Optional[str] = None

    for slug in city["slugs"]:
        test_url = f"{BASE_URL}/{slug}"
        log.info(f"[{city_name}] Trying slug '{slug}' …")
        html = fetch(test_url, delay=DELAY_LIST)
        if html:
            urls = extract_urls_from_page(html)
            if urls:
                working_slug = slug
                for u in urls:
                    if u not in seen:
                        seen.add(u)
                        all_urls.append(u)
                log.info(f"[{city_name}] Slug '{slug}' ✓  page 1 → {len(urls)} URLs")
                break
            else:
                log.info(f"[{city_name}] Slug '{slug}' — page loaded but 0 restaurant URLs")
        time.sleep(1)

    if not working_slug:
        log.warning(f"[{city_name}] No working slug — skipping city")
        return []

    # paginate from page 2
    for page in range(2, MAX_PAGES + 1):
        url  = f"{BASE_URL}/{working_slug}/{page}"
        html = fetch(url, delay=DELAY_LIST)
        if not html:
            log.info(f"[{city_name}] Page {page}: no response — stop")
            break

        urls = extract_urls_from_page(html)
        new  = [u for u in urls if u not in seen]
        if not new:
            log.info(f"[{city_name}] Page {page}: 0 new URLs — stop")
            break

        for u in new:
            seen.add(u)
            all_urls.append(u)
        log.info(f"[{city_name}] Page {page}: +{len(new)}  (total {len(all_urls)})")

        # check for next-page link
        soup     = BeautifulSoup(html, "lxml")
        has_next = bool(
            soup.select_one(f'a[href*="/{working_slug}/{page + 1}"]')
            or soup.select_one('a[rel="next"]')
            or soup.select_one('.pagination .next')
        )
        if not has_next:
            log.info(f"[{city_name}] No next-page link after page {page} — stop")
            break

    log.info(f"[{city_name}] Total URLs collected: {len(all_urls)}")
    return all_urls


# ══════════════════════════════════════════════════════════════════════
#  Detail-page parsing — 16 validated fields
# ══════════════════════════════════════════════════════════════════════

def _extract_json_ld(soup: BeautifulSoup) -> dict:
    food_types = {
        "Restaurant", "FoodEstablishment", "CafeOrCoffeeShop",
        "Bakery", "FastFoodRestaurant", "BarOrPub", "IceCreamShop",
    }
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            t = data.get("@type", "")
            if isinstance(t, list):
                t = t[0]
            if t in food_types:
                return data
        except Exception:
            pass
    return {}


def scrape_detail(url: str, city_name: str) -> Optional[dict]:
    html = fetch(url, delay=DELAY_DET)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    ld   = _extract_json_ld(soup)

    # 1. name
    name = (ld.get("name") or "").strip()
    if not name:
        h1   = soup.select_one("h1")
        name = h1.get_text(strip=True) if h1 else ""
    if not name:
        return None

    # 2. city (injected)
    city = city_name

    # 3. restaurantguru_url
    restaurantguru_url = url

    # 4. address
    ao      = ld.get("address", {})
    address = None
    if isinstance(ao, dict):
        parts   = [ao.get("streetAddress"), ao.get("postalCode"), ao.get("addressLocality")]
        address = ", ".join(p for p in parts if p) or None
    elif isinstance(ao, str):
        address = ao or None

    # 5. geo
    geo = None
    if ld.get("geo"):
        try:
            lat = float(ld["geo"].get("latitude")  or 0)
            lng = float(ld["geo"].get("longitude") or 0)
            if lat != 0 or lng != 0:
                geo = {"lat": lat, "lng": lng}
        except Exception:
            pass

    # 6. phone
    phone = ld.get("telephone") or None
    if not phone:
        tel_el = soup.select_one('a[href^="tel:"]')
        if tel_el:
            phone = tel_el.get("href", "").replace("tel:", "").strip() or None

    # 7. categories (.cuisine_shown span — phrase between address and phone)
    categories: list[str] = [
        s.get_text(strip=True)
        for s in soup.select(".cuisine_shown span")
        if s.get_text(strip=True)
    ]
    if not categories:
        sc = ld.get("servesCuisine", [])
        if isinstance(sc, str):
            sc = [sc]
        categories = [
            (c if isinstance(c, str) else c.get("name", ""))
            for c in sc
            if (c if isinstance(c, str) else c.get("name", ""))
        ]

    # 8. price_level
    price_level = ld.get("priceRange") or None
    if not price_level:
        pr = soup.select_one('[class*="price_range"], [class*="priceRange"]')
        if pr:
            price_level = pr.get_text(strip=True) or None

    # 9. rating
    rating = None
    if ld.get("aggregateRating"):
        try:
            rating = float(ld["aggregateRating"].get("ratingValue") or 0) or None
        except Exception:
            pass

    # 10. reviews
    reviews = None
    if ld.get("aggregateRating"):
        try:
            reviews = int(ld["aggregateRating"].get("reviewCount") or 0) or None
        except Exception:
            pass

    # 11. opening_hours_text
    opening_hours_text = None
    oh_el = soup.select_one(".short_info--top")
    if oh_el:
        opening_hours_text = oh_el.get_text(separator=" ", strip=True) or None
    if not opening_hours_text:
        sched = soup.select_one('[class*="schedule"], [class*="hours"]')
        if sched:
            opening_hours_text = sched.get_text(separator=" ", strip=True) or None

    # 12. photo_url
    photo_url = None
    img_ld    = ld.get("image")
    if img_ld:
        photo_url = img_ld[0] if isinstance(img_ld, list) else img_ld
    if not photo_url:
        for im in soup.select("img[src]"):
            src = im.get("src", "")
            if src and (".jpg" in src.lower() or ".webp" in src.lower()):
                if any(kw in src for kw in ("restaurantguru", "cdn", "media")):
                    photo_url = src
                    break

    # 13. zone (addressRegion)
    zone = None
    if isinstance(ao, dict):
        zone = ao.get("addressRegion") or ao.get("addressLocality") or None

    # 14. tags
    tags: list[str] = [
        t.get_text(strip=True)
        for t in soup.select(".tag.txt_hint")
        if t.get_text(strip=True)
    ]

    # 15. features (.feature_item without class "none")
    features: list[str] = []
    for f in soup.select(".feature_item"):
        if "none" in (f.get("class") or []):
            continue
        text = f.get_text(strip=True)
        if text:
            features.append(text)

    # 16. description
    description = None
    desc_el     = soup.select_one(".wrapper_description .description")
    if desc_el:
        description = desc_el.get_text(separator=" ", strip=True) or None
    if not description:
        description = (ld.get("description") or "").strip() or None

    return {
        "name":               name,
        "city":               city,
        "restaurantguru_url": restaurantguru_url,
        "address":            address,
        "geo":                geo,
        "phone":              phone,
        "categories":         categories,
        "price_level":        price_level,
        "rating":             rating,
        "reviews":            reviews,
        "opening_hours_text": opening_hours_text,
        "photo_url":          photo_url,
        "zone":               zone,
        "tags":               tags,
        "features":           features,
        "description":        description,
        "source":             "restaurantguru",
    }


# ══════════════════════════════════════════════════════════════════════
#  MongoDB
# ══════════════════════════════════════════════════════════════════════

def get_collection():
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI manquant dans .env")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    col = client[MONGODB_DB][COLLECTION]
    col.create_index([("name", 1), ("city", 1)], unique=True, background=True)
    col.create_index([("city", 1)])
    col.create_index([("rating", -1)])
    col.create_index([("source", 1)])
    return col


def upsert_batch(col, docs: list[dict]) -> tuple[int, int]:
    if not docs:
        return 0, 0
    ops = [
        UpdateOne(
            {"name": d["name"], "city": d["city"]},
            {"$set": d},
            upsert=True,
        )
        for d in docs
    ]
    try:
        r = col.bulk_write(ops, ordered=False)
        return r.upserted_count, r.modified_count
    except BulkWriteError as e:
        log.error(f"BulkWriteError: {e.details.get('writeErrors', [])[:3]}")
        return 0, 0


# ══════════════════════════════════════════════════════════════════════
#  Progress persistence
# ══════════════════════════════════════════════════════════════════════

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════════════
#  Scrape one city
# ══════════════════════════════════════════════════════════════════════

def scrape_city(city: dict, col, already_done: set[str], progress: dict) -> dict:
    name = city["name"]

    all_urls = collect_city_urls(city)
    pending  = [u for u in all_urls if u not in already_done]
    skipped  = len(all_urls) - len(pending)

    log.info(
        f"[{name}] {len(all_urls)} URLs found — "
        f"{len(pending)} to scrape, {skipped} already done"
    )

    scraped = 0
    errors  = 0
    batch: list[dict] = []

    for i, url in enumerate(pending, 1):
        doc = scrape_detail(url, name)
        if doc:
            batch.append(doc)
            already_done.add(url)
            scraped += 1
        else:
            errors += 1
            log.warning(f"[{name}] ✗ ({i}/{len(pending)}) {url}")

        if len(batch) >= BATCH_DB:
            ins, upd = upsert_batch(col, batch)
            log.info(
                f"[{name}] [{i}/{len(pending)}] "
                f"uploaded {len(batch)}  (+{ins} new / ~{upd} updated)"
            )
            batch = []
            # save progress after every batch so resume works mid-city
            progress["done_urls"] = list(already_done)
            save_progress(progress)

    if batch:
        ins, upd = upsert_batch(col, batch)
        log.info(f"[{name}] Final batch: {len(batch)}  (+{ins} new / ~{upd} updated)")

    return {"city": name, "urls": len(all_urls), "scraped": scraped, "errors": errors}


# ══════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 62)
    log.info("  fetch_restaurant_from_guru.py")
    log.info(f"  DB  : {MONGODB_DB}.{COLLECTION}")
    log.info(f"  Cities: {[c['name'] for c in CITIES]}")
    log.info("=" * 62)

    try:
        col = get_collection()
        log.info("MongoDB Atlas connected ✓")
    except Exception as exc:
        log.error(f"MongoDB connection failed: {exc}")
        sys.exit(1)

    progress     = load_progress()
    already_done: set[str] = set(progress.get("done_urls", []))
    log.info(f"Progress: {len(already_done)} URLs already scraped (resumable)")

    summary: list[dict] = []

    for city in CITIES:
        log.info(f"\n{'─' * 55}")
        log.info(f"  {city['name'].upper()}")
        log.info(f"{'─' * 55}")

        stats = scrape_city(city, col, already_done, progress)
        summary.append(stats)

        progress["done_urls"] = list(already_done)
        save_progress(progress)

        log.info(
            f"[{city['name']}] ✓ {stats['scraped']} scraped  "
            f"| {stats['errors']} errors"
        )

        if city is not CITIES[-1]:
            log.info("Pausing 3s …")
            time.sleep(3)

    # ── final report ────────────────────────────────────────────────
    log.info("\n" + "=" * 62)
    log.info("  FINAL REPORT")
    log.info("=" * 62)
    tot_scraped = sum(s["scraped"] for s in summary)
    tot_errors  = sum(s["errors"]  for s in summary)

    for s in summary:
        icon = "✓" if s["errors"] == 0 else "⚠"
        log.info(
            f"  {icon} {s['city']:12s}  {s['urls']:3d} URLs  "
            f"{s['scraped']:3d} scraped  {s['errors']:2d} errors"
        )

    log.info(f"\n  TOTAL : {tot_scraped} scraped  |  {tot_errors} errors")

    try:
        rg_count = col.count_documents({"source": "restaurantguru"})
        log.info(f"  DB (restaurantguru): {rg_count} documents total")
    except Exception:
        pass

    log.info("=" * 62)

    if tot_errors == 0 and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        log.info("Progress file removed (clean run).")


if __name__ == "__main__":
    main()
