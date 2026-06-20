from dotenv import load_dotenv
import os

load_dotenv()


API_KEY = os.getenv("API_KEY")
TRAVELLER_API_URL = os.getenv("TRAVELER_API_URL")

# Profil Loader
TRAVELLER_MANAGEMENT_API_URL = os.getenv("TRAVELLER_MANAGEMENT")
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

# --- Ranking weights (doivent sommer à 1.0)
USER_SCORE_WEIGHT     = float(os.getenv("USER_SCORE_WEIGHT",     "0.70"))
BUSINESS_SCORE_WEIGHT = float(os.getenv("BUSINESS_SCORE_WEIGHT", "0.30"))