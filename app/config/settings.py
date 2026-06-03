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



# --- Logistics 
OPENWEATHER_API_KEY= os.getenv("OPENWEATHER_API_KEY")
GOOGLE_MAPS_API_KEY= os.getenv("GOOGLE_MAPS_API_KEY")
OPENWEATHER_BASE_URL= os.getenv("OPENWEATHER_BASE_URL")
GOOGLE_MAPS_BASE_URL= os.getenv("GOOGLE_MAPS_BASE_URL")