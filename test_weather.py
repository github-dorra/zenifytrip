import asyncio

from app.nodes.Logistics.wearth_node import WeatherNode


async def main():

    node = WeatherNode()

    state = {
        "destination": "Sousse",
        "language": "fr",
        "time_reference": "today"
    }

    result = await node(state)

    print("\n===== WEATHER RESULT =====\n")

    weather = result["weather_context"]

    print(weather)

    print("\n===== INSIGHTS =====\n")

    print(weather.insights)


if __name__ == "__main__":
    asyncio.run(main())