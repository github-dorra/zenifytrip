from dotenv import load_dotenv
import os

load_dotenv()


API_KEY = os.getenv("API_KEY")
TRAVELLER_API_URL = os.getenv("TRAVELER_API_URL")

# Profil Loader
TRAVELLER_MANAGEMENT_API_URL = os.getenv("TRAVELLER_MANAGEMENT")
TRAVELLER_MANAGEMENT_BY_VOUCHER = os.getenv("TRAVELLER_MANAGEMENT_BY_VOUCHER")
TRAVEL_PLAN_MANAGEMENT_URL = os.getenv("TRAVEL_PLAN_MANAGEMENT_URL")

# --- Hotel recommendation
HOTEL_API_URL = os.getenv("HOTEL_API_URL")
HOTEL_SERVICE_API_URL = os.getenv("HOTEL_SERVICE_API_URL")
ZONES_API_URL = os.getenv("ZONES_API_URL")

# --- Flight recommendation
FLIGHTS_API_URL = os.getenv("FLIGHTS_API_URL")
AIRPORTS_API_URL = os.getenv("AIRPORTS_API_URL")
AIRLINES_API_URL = os.getenv("AIRLINES_API_URL")

# --- Activity recommendation
BOOKINGS_API_URL = os.getenv("BOOKINGS_API_URL")
ACTIVITIES_API_URL = os.getenv("ACTIVITIES_API_URL")



# --- Logistics
OPENWEATHER_API_KEY= os.getenv("OPENWEATHER_API_KEY")
GOOGLE_MAPS_API_KEY= os.getenv("GOOGLE_MAPS_API_KEY")
OPENWEATHER_BASE_URL= os.getenv("OPENWEATHER_BASE_URL")
GOOGLE_MAPS_BASE_URL= os.getenv("GOOGLE_MAPS_BASE_URL")

# --- Restaurant Approach C
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# --- MongoDB Atlas
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "zenifytrip")

# ══════════════════════════════════════════════════════════════════════════════
# RÈGLE CRITIQUE — Centralisation des valeurs globales
# ──────────────────────────────────────────────────────────────────────────────
# Toute valeur susceptible de changer selon un abonnement, un plan cloud,
# une limite API, ou utilisée à plusieurs endroits dans le projet DOIT être
# déclarée ici et importée depuis ici.
# Ne jamais hardcoder une valeur critique directement dans un node ou service.
# ══════════════════════════════════════════════════════════════════════════════

# --- Redis
REDIS_HOST=os.getenv("REDIS_HOST")
REDIS_PORT=os.getenv("REDIS_PORT")
REDIS_USERNAME=os.getenv("REDIS_USERNAME")
REDIS_PASSWORD=os.getenv("REDIS_PASSWORD")

# Redis connection pool — à ajuster selon le plan Redis souscrit :
#   Free tier Redis Cloud    → 30 connexions max  → REDIS_MAX_CONNECTIONS=25
#   Plan 100MB payant        → 100+ connexions    → REDIS_MAX_CONNECTIONS=80
#   Valeur actuelle (50)     → couvre ~16 workers Gunicorn avec marge de sécurité
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))

# Cache Keys
REDIS_ENV = os.getenv("REDIS_ENV", "dev")        # dev | staging | prod — à définir dans .env
PROFILE_CACHE_PREFIX = f"{REDIS_ENV}:profile"    # ex: dev:profile:abc-123 / prod:profile:abc-123

# TTL CACHE PROFILE IN REDIS
# Voyage futur  : TTL = (returnDate - now) + EXTRA  (max MAX_TTL)
# Voyage passé  : TTL = EXTRA (fallback)
# Maximum       : 30 jours
PROFILE_CACHE_DEFAULT_TTL_SECONDS      = 7  * 24 * 3600   # 7 jours  — fallback voyage passé
PROFILE_CACHE_MAX_TTL_SECONDS          = 30 * 24 * 3600   # 30 jours — plafond absolu
PROFILE_CACHE_EXTRA_SECONDS_AFTER_RETURN = 2 * 24 * 3600  # 2 jours  — buffer post-retour

# --- Ranking weights (doivent sommer à 1.0)
USER_SCORE_WEIGHT     = float(os.getenv("USER_SCORE_WEIGHT",     "0.70"))
BUSINESS_SCORE_WEIGHT = float(os.getenv("BUSINESS_SCORE_WEIGHT", "0.30"))

# --- Facteur de disponibilité dynamique (ranking_node V2)
# Appliqué au ranked_score des candidats à dispo INCONNUE (is_available=None, ex. SOURCE 2 MongoDB).
# Le facteur est choisi dynamiquement selon la force du meilleur candidat CONFIRMÉ (agence, is_available=True) :
#   meilleur user_score agence >= SEUIL → facteur PROTECTED (agence forte → protection commerciale,
#                                          mathématiquement imbattable par MongoDB : 1.0×0.815×0.60=0.489 < 0.60×0.954=0.572)
#   meilleur user_score agence <  SEUIL ou aucune agence → facteur OPEN (MongoDB remonte librement)
AVAILABILITY_AGENCY_STRONG_THRESHOLD  = float(os.getenv("AVAILABILITY_AGENCY_STRONG_THRESHOLD",  "0.60"))
AVAILABILITY_UNKNOWN_FACTOR_PROTECTED = float(os.getenv("AVAILABILITY_UNKNOWN_FACTOR_PROTECTED", "0.60"))
AVAILABILITY_UNKNOWN_FACTOR_OPEN      = float(os.getenv("AVAILABILITY_UNKNOWN_FACTOR_OPEN",      "0.90"))

# --- Seuil de basculement Tier 1 (Mongo) -> Tier 2 (Google Places) restaurant_service.py
RESTAURANT_MONGO_MIN_RESULTS = int(os.getenv("RESTAURANT_MONGO_MIN_RESULTS", "3"))