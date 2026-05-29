from pydantic import BaseModel, Field
from typing import Optional, List

#  Représenter la météo telle qu’elle existe dans OpenWeather   ->  données brutes
class WeatherForecast(BaseModel):
    date: str
    temperature_high: Optional[float] = None
    temperature_low: Optional[float] = None
    description: Optional[str] = None
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    icon: Optional[str] = None
    
    
#  transforme ces données brutes a des données exploitables par les nodes suivantes 
# intelligence  ---> scoring 
class WeatherInsights(BaseModel):

    # --- TEMPERATURES REELLES ---
    temperature_high: Optional[float] = None   # max du jour
    temperature_low: Optional[float] = None    # min du jour
    avg_temperature: float = 0.0               # moyenne (high+low)/2

    # --- RAW DATA ---
    rain_probability: float = 0.0
    cloudy_ratio: float = 0.0
    wind_speed: float = 0.0

    # --- INTELLIGENCE FLAGS ---
    is_hot_day: bool = False
    is_rainy_day: bool = False
    is_sunny_day: bool = False
    is_cloudy_day: bool = False
    is_windy_day: bool = False

    # --- SCORES (for ranking agent) ---
    beach_score: float = 0.0
    outdoor_score: float = 0.0
    indoor_score: float = 0.0


# orchestrator input : decision finale
class WeatherContext(BaseModel):

    available: bool = False

    city: Optional[str] = None

    forecast: List[WeatherForecast] = Field(default_factory=list)

    insights: Optional[WeatherInsights] = None

    weather_summary: Optional[str] = None