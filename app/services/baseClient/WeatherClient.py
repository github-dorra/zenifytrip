import logging
from typing import List, Optional

from app.config.settings import (
    OPENWEATHER_API_KEY,
    OPENWEATHER_BASE_URL,
)
from app.schemas.weather_schema import WeatherForecast
from app.services.baseClient.base import BaseAPIClient

logger = logging.getLogger(__name__)


class WeatherClient(BaseAPIClient):
    """
    Low-level OpenWeather client.
    api CALL
    Data brut recupered 
    DATA transfer to weatherForecast
    """

    #initiation
    def __init__(self):
        super().__init__(
            base_url=OPENWEATHER_BASE_URL,
            timeout=15.0,
            max_retries=2,
            retry_delay=0.5,
        )
        
    async def get_current_weather_by_city(
        self,
        city: str,
        lang: str = "fr",
    ) -> Optional[WeatherForecast]:
        """Météo actuelle via /weather — températures réelles du moment."""

        if not OPENWEATHER_API_KEY or not city:
            return None

        data = await self._get(
            "/weather",
            params={
                "q": city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": lang,
            },
        )

        if not data:
            return None

        from datetime import datetime
        main    = data.get("main", {}) or {}
        weather = (data.get("weather") or [{}])[0] or {}
        wind    = data.get("wind", {}) or {}

        return WeatherForecast(
            date=datetime.utcnow().strftime("%Y-%m-%d"),
            temperature_high=main.get("temp_max"),
            temperature_low=main.get("temp_min"),
            description=weather.get("description"),
            humidity=main.get("humidity"),
            wind_speed=wind.get("speed"),
        )

    # forecast par ville
    async def get_forecast_by_city(
        self,
        city: str,
        lang: str = "fr",
    ) -> List[WeatherForecast]:

        if not OPENWEATHER_API_KEY:
            logger.warning("Missing OpenWeather API key")
            return []

        if not city:
            return []

        # appel api 
        data = await self._get(
           "/forecast",
            params={
                "q": city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": lang,
                "cnt": 40,            # 40 points = 5j
            },
        )

        if not data or "list" not in data:
            return []

        return self._parse_forecast(data["list"])

    async def get_forecast_by_coordinates(
        self,
        lat: float,
        lon: float,
        lang: str = "fr",
    ) -> List[WeatherForecast]:

        if not OPENWEATHER_API_KEY:
            logger.warning("Missing OpenWeather API key")
            return []

        if lat is None or lon is None:
            return []

        data = await self._get(
            "/forecast",
            params={
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": lang,
                "cnt": 40,
            },
        )

        if not data or "list" not in data:
            return []

        return self._parse_forecast(data["list"])

    # ---------------------------
    # INTERNAL PARSER
    # ---------------------------

    def _parse_forecast(self, forecast_list: list) -> List[WeatherForecast]:

        daily = {}

        for entry in forecast_list:
            dt_txt = entry.get("dt_txt", "")
            if not dt_txt:
                continue

            date = dt_txt.split(" ")[0]

            
            # base meteo/j
            if date not in daily:
                daily[date] = {
                    "highs": [],
                    "lows": [],
                    "descriptions": [],
                    "wind": [],
                    "humidity": [],
                }

            main = entry.get("main", {}) or {}
            weather = (entry.get("weather") or [{}])[0] or {}
            wind = entry.get("wind", {}) or {}

            if main.get("temp_max") is not None:
                daily[date]["highs"].append(main["temp_max"])

            if main.get("temp_min") is not None:
                daily[date]["lows"].append(main["temp_min"])

            if weather.get("description"):
                daily[date]["descriptions"].append(weather["description"])

            if wind.get("speed") is not None:
                daily[date]["wind"].append(wind["speed"])

            if main.get("humidity") is not None:
                daily[date]["humidity"].append(main["humidity"])

        results = []

        for date, info in sorted(daily.items()):

            forecast = WeatherForecast(
                date=date,
                temperature_high=max(info["highs"]) if info["highs"] else None,
                temperature_low=min(info["lows"]) if info["lows"] else None,
                description=info["descriptions"][0] if info["descriptions"] else None,
                wind_speed=(
                    sum(info["wind"]) / len(info["wind"])
                    if info["wind"]
                    else None
                ),
                humidity=(
                    sum(info["humidity"]) / len(info["humidity"])
                    if info["humidity"]
                    else None
                ),
                icon=None,
            )

            results.append(forecast)

        return results