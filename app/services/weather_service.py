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
        date: Optional[str] = None,
    ) -> WeatherContext:

        target_date = date or self._get_today_date()
        today       = self._get_today_date()
        use_current = (target_date == today)

        date_forecasts: List[WeatherForecast] = []

        # ── TODAY → /weather (real-time temp_max/temp_min for the full day) ──
        if use_current:
            if city:
                forecast = await self.weather_client.get_current_weather_by_city(
                    city=city, lang=lang
                )
                if forecast:
                    date_forecasts = [forecast]
            elif lat is not None and lon is not None:
                # /weather by coordinates not yet in client → fall through to forecast
                pass

            # coordinates fallback or city failed → try geo-IP then /forecast
            if not date_forecasts:
                if lat is not None and lon is not None:
                    forecasts = await self.weather_client.get_forecast_by_coordinates(
                        lat=lat, lon=lon, lang=lang
                    )
                elif city:
                    forecasts = await self.weather_client.get_forecast_by_city(
                        city=city, lang=lang
                    )
                else:
                    geo = await self.map_service.get_user_location()
                    forecasts = (
                        await self.weather_client.get_forecast_by_coordinates(
                            lat=geo["lat"], lon=geo["lng"], lang=lang
                        )
                        if geo else []
                    )
                date_forecasts = [f for f in forecasts if f.date == today] or forecasts[:1]

        # ── FUTURE DATE → /forecast ──
        else:
            if lat is not None and lon is not None:
                forecasts = await self.weather_client.get_forecast_by_coordinates(
                    lat=lat, lon=lon, lang=lang
                )
            elif city:
                forecasts = await self.weather_client.get_forecast_by_city(
                    city=city, lang=lang
                )
            else:
                geo = await self.map_service.get_user_location()
                forecasts = (
                    await self.weather_client.get_forecast_by_coordinates(
                        lat=geo["lat"], lon=geo["lng"], lang=lang
                    )
                    if geo else []
                )
            date_forecasts = [f for f in forecasts if f.date == target_date] or forecasts[:1]

        if not date_forecasts:
            return WeatherContext(
                available=False,
                forecast=[],
                weather_summary="Météo indisponible",
            )

        insights = self._build_insights(date_forecasts)
        return WeatherContext(
            available=True,
            forecast=date_forecasts,
            insights=insights,
            weather_summary=self._build_summary(insights),
        )
    
    
    def _build_insights(self, forecasts: List[WeatherForecast]) -> WeatherInsights:
        rain_keywords    = ["rain", "pluie", "storm", "orage", "drizzle", "bruine", "averses", "thunderstorm", "snow", "neige", "blizzard", "verglas", "vent"]
        sun_keywords     = ["sun", "clear", "ensoleillé", "ciel dégagé", "soleil"]
        cloudy_keywords  = ["clouds", "nuageux", "nuages", "overcast", "couvert", "brume", "mist", "fog"]

        highs = []
        lows  = []
        rain_score = sun_score = cloudy_score = 0

        for f in forecasts:
            if f.temperature_high is not None:
                highs.append(f.temperature_high)
            if f.temperature_low is not None:
                lows.append(f.temperature_low)

            desc = (f.description or "").lower()
            if any(w in desc for w in rain_keywords):
                rain_score += 1
            if any(w in desc for w in sun_keywords):
                sun_score += 1
            if any(w in desc for w in cloudy_keywords):
                cloudy_score += 1

        temperature_high = max(highs) if highs else None
        temperature_low  = min(lows)  if lows  else None
        avg_temp = (
            (temperature_high + temperature_low) / 2
            if temperature_high is not None and temperature_low is not None
            else (temperature_high or temperature_low or 0.0)
        )

        n = len(forecasts) or 1
        rain_probability = rain_score  / n
        sun_ratio        = sun_score   / n
        cloudy_ratio     = cloudy_score / n

        is_hot_day    = avg_temp >= 32
        is_rainy_day  = rain_probability > 0.4
        is_sunny_day  = sun_ratio > 0.4
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
        
        return WeatherInsights(
            temperature_high=temperature_high,
            temperature_low=temperature_low,
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
        )
    def _build_summary(self, insights: WeatherInsights) -> str:
        high = f"{round(insights.temperature_high, 1)}°C" if insights.temperature_high is not None else "N/A"
        low  = f"{round(insights.temperature_low,  1)}°C" if insights.temperature_low  is not None else "N/A"
        return (
            f"Température max: {high}, min: {low}. "
            f"Probabilité de pluie: {round(insights.rain_probability * 100)}%."
        )
        
        