from typing import Optional, List
from datetime import datetime, timedelta

from app.schemas.weather_schema import (
    WeatherForecast,
    WeatherInsights,
    WeatherContext,
)

from app.services.baseClient.WeatherClient import WeatherClient
from app.services.Map_service import MapService

class WeatherService:
    """
    High-level Weather Intelligence Service.

    Role:
    - fallback geo if city missing
    - call WeatherClient
    - compute tourism insights
    - build WeatherContext for agents
    """

    def __init__(self):
        self.weather_client = WeatherClient()
        self.map_service = MapService()
        
    def _get_today_date(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    async def get_weather_context(
        self,
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        lang: str = "fr",
    ) -> WeatherContext:
        
        # fallback intelligent en cas ou ville manquante 
        forecasts: List[WeatherForecast] = []

        # CASE 1: coordinates available (BEST CASE)
        if lat is not None and lon is not None:
            forecasts = await self.weather_client.get_forecast_by_coordinates(
                lat=lat,
                lon=lon,
                lang=lang,
            )

        # CASE 2: city available
        elif city:
            forecasts = await self.weather_client.get_forecast_by_city(
                city=city,
                lang=lang,
            )

        # CASE 3: NOTHING → use GEO fallback
        else:
            geo = await self.map_service.get_user_location()

            if geo:
                forecasts = await self.weather_client.get_forecast_by_coordinates(
                    lat=geo.lat,
                    lon=geo.lng,
                    lang=lang,
                ) 
                
        if not forecasts:
            return WeatherContext(
                available=False,
                forecast=[],
                weather_summary="Météo indisponible",
                prefer_indoor=False,
                avoid_boat_trip=False,
                avoid_long_walks=False,
            )
            
        #insights = self._build_insights(forecasts) # pour 5 j 
        today = self._get_today_date()              # actuel 

        today_forecasts = [
            f for f in forecasts
            if f.date == today
        ]
        
        if not today_forecasts:
            today_forecasts = forecasts[:1]  # fallback sécurité
            
        insights = self._build_insights(today_forecasts)
        return WeatherContext(
            available=True,
            forecast=today_forecasts, # forecasts
            insights=insights,
            weather_summary=self._build_summary(insights),
        )
    
    
    def _build_insights(self, forecasts: List[WeatherForecast]) -> WeatherInsights:
        temps = []
        rain_keywords= ["rain", "pluie", "storm", "orage", "drizzle", "bruine", "averses", "thunderstorm","snow", "neige", "blizzard", "verglas","vent"]
        sun_keywords= ["sun", "clear", "ensoleillé", "ciel dégagé", "soleil"]
        cloudy_keywords= ["clouds", "nuageux", "nuages", "overcast", "couvert", "brume", "mist", "fog"]

        
        rain_score = 0
        sun_score = 0
        cloudy_score = 0
        
        
        for f in forecasts:
            if f.temperature_high and f.temperature_low:
                temps.append((f.temperature_high + f.temperature_low) / 2)

            desc = (f.description or "").lower()

            if any(w in desc for w in rain_keywords):
                rain_score += 1

            if any(w in desc for w in sun_keywords):
                sun_score += 1
                
            if any(w in desc for w in cloudy_keywords):
                cloudy_score += 1
            
                
        avg_temp = sum(temps) / len(temps) if temps else 0
        rain_probability = rain_score  / len(forecasts) if forecasts else 0
        sun_ratio =  sun_score / len(forecasts) if forecasts else 0
        cloudy_ratio = cloudy_score / len(forecasts) if forecasts else 0
        
        is_hot_day = avg_temp >= 32
        is_rainy_day = rain_probability > 0.4
        is_sunny_day = sun_ratio > 0.4
        is_cloudy_day = cloudy_ratio > 0.4
        
        



        beach_score = (
            0.4
            + (0.3 if 22 <= avg_temp <= 32 else 0)            # chaleur entre 22 -32 °c
            + (0.2 if sun_ratio > 0.4 else 0)                 #+ soleillé
            - (0.4 if rain_probability > 0.3 else 0)          #- pluie
        ) 
        
        #   -> plage ok ou pas 
        
        outdoor_score = (
            0.5
            + (0.2 if 18 <= avg_temp <= 30 else 0)
            - (0.4 if rain_probability > 0.4 else 0)
        )
        
        indoor_score = (
            0.4
            + (0.4 if rain_probability > 0.4 else 0)
            + (0.2 if avg_temp > 34 else 0)
        )
        
        recommendation = max(
            {
                "beach": beach_score,
                "outdoor": outdoor_score,
                "indoor": indoor_score,
            },
            key=lambda k: {
                "beach": beach_score,
                "outdoor": outdoor_score,
                "indoor": indoor_score,
            }[k],
        )
        return WeatherInsights(
            avg_temperature=avg_temp,
            rain_probability=rain_probability,
            cloudy_ratio=cloudy_ratio,

            is_hot_day=is_hot_day,
            is_rainy_day=is_rainy_day,
            is_sunny_day=is_sunny_day,
            is_cloudy_day=is_cloudy_day,

            beach_score=beach_score,
            outdoor_score=outdoor_score,
            indoor_score=indoor_score,

            recommendation_hint=recommendation,
    )
    def _build_summary(
        self,
        insights: WeatherInsights,
    ) -> str:

        return (
            f"Température moyenne {insights.avg_temperature}°C. "
            f"Tendance météo: {insights.recommendation_hint}. "
            f"Probabilité de pluie: {round(insights.rain_probability * 100)}%."
        )
        
        