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


def ensure_indexes():
    """
    Crée les index nécessaires sur les deux collections.
    Idempotent — safe à appeler plusieurs fois.
    """
    # activities : unicité (name, destination_id) + recherche par tags/rating
    act = activities_collection()
    act.create_indexes([
        IndexModel([("name", ASCENDING), ("destination_id", ASCENDING)], unique=True),
        IndexModel([("destination_id", ASCENDING)]),
        IndexModel([("tags", ASCENDING)]),
        IndexModel([("rating", ASCENDING)]),
        IndexModel([("traveler_types", ASCENDING)]),
        IndexModel([("price_from_eur", ASCENDING)]),
    ])

    # restaurants : unicité (name, destination_id) + recherche par prix/rating
    rest = restaurant_collection()
    rest.create_indexes([
        IndexModel([("name", ASCENDING), ("destination_id", ASCENDING)], unique=True),
        IndexModel([("destination_id", ASCENDING)]),
        IndexModel([("rating", ASCENDING)]),
        IndexModel([("price_level", ASCENDING)]),
    ])
    logger.info("Index MongoDB créés / vérifiés")
