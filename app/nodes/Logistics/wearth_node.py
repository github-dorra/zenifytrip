# Ajouter le contexte météo
import logging
from typing import Dict, Any

from app.services.weather_service import WeatherService
from app.schemas.weather_schema import WeatherContext

logger = logging.getLogger(__name__)


class WeatherNode:
    """
    LangGraph Weather Node.

    Responsibilities:
    - read destination info from state
    - call WeatherService
    - inject WeatherContext into workflow state
    - never crash graph
    """

    def __init__(self):
        self.weather_service = WeatherService()

    async def __call__(
        self,
        state: Dict[str, Any],
    ) -> Dict[str, Any]:

        try:
            # -----------------------------
            # READ DATA FROM STATE
            # -----------------------------

            #merged_context = state.get("merged_context")
            #intent_result = state.get("intent_result")
            #city= merged_context.get("destination")
            
            #lang = intent_result.get("language", "fr")
            
            city = state.get("destination")
            lang = state.get("language", "fr")


            logger.info(
                f"WeatherNode started | city={city}"
            )

            # -----------------------------
            # CALL WEATHER SERVICE
            # -----------------------------

            weather_context: WeatherContext = (
                await self.weather_service.get_weather_context(
                    city=city,
                    lang=lang,
                )
            )

            # -----------------------------
            # UPDATE STATE
            # -----------------------------

            state["weather_context"] = weather_context

            logger.info(
                f"WeatherNode success | available={weather_context.available}"
            )

            return state

        except Exception as e:

            logger.exception(
                f"WeatherNode failed | error={type(e).__name__}: {e}"
            )

            # IMPORTANT:
            # LangGraph workflow should continue
            # even if weather API fails

            state["weather_context"] = WeatherContext(
                available=False,
                forecast=[],
                weather_summary="Weather unavailable",
                insights=None,
            )

            return state


