from pymongo import MongoClient, IndexModel, ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database
import logging

logger = logging.getLogger(__name__)

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Retourne le client MongoDB Atlas (singleton)."""
    global _client
    if _client is None:
        from app.config.settings import MONGODB_URI, MONGODB_DB
        if not MONGODB_URI:
            raise ValueError("MONGODB_URI manquant dans .env")
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        logger.info(f"MongoDB Atlas connecté — base : {MONGODB_DB}")
    return _client


def get_db() -> Database:
    from app.config.settings import MONGODB_DB
    return get_client()[MONGODB_DB]


def get_collection(name: str) -> Collection:
    return get_db()[name]


def activities_collection() -> Collection:
    return get_collection("activities_collection")


def restaurant_collection() -> Collection:
    return get_collection("restaurant_collection")


def traveller_profile_collection() -> Collection:
    """Cache profil voyageur — remplace Redis profile:{traveller_id} (migration 2026-07-28)."""
    return get_collection("traveller_profile_cache")


def traveller_preferences_collection() -> Collection:
    """
    Préférences d'onboarding (trip_type, travel_purpose, culinary_interests) —
    donnée ZenifyTrip propre et durable, PAS un cache (contrairement à
    traveller_profile_cache) : keyée sur user_id, aucune expiration, fonctionne
    pour USER RÉEL et USER NATIF indépendamment d'un traveller_id agence.
    """
    return get_collection("traveller_preferences")


def ensure_indexes():
    """
    Crée les index nécessaires sur les deux collections.
    Idempotent — safe à appeler plusieurs fois.
    """
    # activities : unicité (name, destination_id) + recherche par tags/rating
    act = activities_collection()
    act.create_indexes([
        # Unicité
        IndexModel([("name", ASCENDING), ("destination_id", ASCENDING)], unique=True),
        # Champs simples (compatibilité existante)
        IndexModel([("destination_id", ASCENDING)]),
        IndexModel([("tags", ASCENDING)]),
        IndexModel([("rating", ASCENDING)]),
        IndexModel([("traveler_types", ASCENDING)]),
        IndexModel([("price_from_eur", ASCENDING)]),
        # Compound — requête principale avec tri
        IndexModel(
            [("destination_id", ASCENDING), ("type", ASCENDING), ("rating", ASCENDING)],
            name="idx_dest_type_rating",
        ),
        # Compound — filtre météo indoor/outdoor
        IndexModel(
            [("destination_id", ASCENDING), ("type", ASCENDING), ("indoor", ASCENDING)],
            name="idx_dest_type_indoor",
        ),
        # Compound — filtre audience (famille/couple/solo)
        IndexModel(
            [("destination_id", ASCENDING), ("type", ASCENDING), ("audience", ASCENDING)],
            name="idx_dest_type_audience",
        ),
        # Compound — filtre activity_type
        IndexModel(
            [("destination_id", ASCENDING), ("type", ASCENDING), ("activity_type", ASCENDING), ("rating", ASCENDING)],
            name="idx_dest_type_acttype_rating",
        ),
        # Day-trips depuis une ville voisine
        IndexModel(
            [("nearby", ASCENDING), ("type", ASCENDING), ("rating", ASCENDING)],
            name="idx_nearby_type_rating",
        ),
    ])

    # restaurants (RestaurantGuru) : unicité (name, city) + recherche par city/zone/rating
    rest = restaurant_collection()

    # Supprimer l'ancien index (name, destination_id) si présent — conflictuel avec
    # les docs RestaurantGuru qui n'ont pas de destination_id (tous null → doublon)
    try:
        existing = rest.index_information()
        if "name_1_destination_id_1" in existing:
            rest.drop_index("name_1_destination_id_1")
            logger.info("restaurant_collection: ancien index name_1_destination_id_1 supprimé")
    except Exception as e:
        logger.warning(f"restaurant_collection: impossible de supprimer l'ancien index: {e}")

    rest.create_indexes([
        # Unicité sur (name, city) — adapté aux données RestaurantGuru
        IndexModel([("name", ASCENDING), ("city", ASCENDING)], unique=True),
        # Recherche par ville et gouvernorat — utilisés par MongoRestaurantService
        IndexModel([("city",   ASCENDING)]),
        IndexModel([("zone",   ASCENDING)]),
        # Tri et filtrage
        IndexModel([("rating",      ASCENDING)]),
        IndexModel([("price_level", ASCENDING)]),
        IndexModel([("source",      ASCENDING)]),
    ])

    # traveller_profile_cache : cache profil voyageur (remplace Redis).
    # Index TTL natif sur expires_at — MongoDB supprime le doc une fois expire_at
    # dépassé (sweep périodique ~60s, équivalent fonctionnel du SETEX Redis).
    # _id = traveller_id directement -> pas de champ/index dédié nécessaire.
    profile_cache = traveller_profile_collection()
    profile_cache.create_indexes([
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
    ])

    logger.info("Index MongoDB créés / vérifiés")
