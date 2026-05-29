import asyncio
from typing import Dict, Any

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.services.weather_service import WeatherService
from app.schemas.weather_schema import WeatherContext


class WeatherNode(BaseNode):

    def __init__(self):
        super().__init__(NodeConfig(
            name="weather_node",
            node_type="tool_node",
        ))
        self.weather_service = WeatherService()

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        merged_context = state.get("merged_context", {})
        intent_result  = state.get("intent_result", {})

        city = merged_context.get("destination")
        date = merged_context.get("start_date")
        lang = intent_result.get("language", "fr") if isinstance(intent_result, dict) else "fr"

        self.logger.info(f"city={city} | date={date} | lang={lang}")

        try:
            weather_context: WeatherContext = asyncio.run(
                self.weather_service.get_weather_context(
                    city=city,
                    lang=lang,
                    date=date,
                )
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                weather_context = loop.run_until_complete(
                    self.weather_service.get_weather_context(city=city, lang=lang, date=date)
                )
            finally:
                loop.close()
        except Exception as e:
            self.logger.error(f"WeatherService error: {e}")
            weather_context = WeatherContext(available=False, forecast=[])

        return {
            "weather_context": weather_context.model_dump(),
        }
