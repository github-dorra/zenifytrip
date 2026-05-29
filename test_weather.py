from app.nodes.Logistics.weather_node import WeatherNode


def main():

    node = WeatherNode()

    state = {
        "merged_context": {
            "destination": "Monastir",
        },
        "intent_result": {
            "language": "fr",
        },
    }

    result = node(state)

    print("\n===== WEATHER RESULT =====\n")

    weather = result.get("weather_context", {})

    print("available        :", weather.get("available"))
    print("weather_summary  :", weather.get("weather_summary"))

    print("\n===== INSIGHTS =====\n")

    insights = weather.get("insights") or {}
    print("avg_temperature  :", insights.get("avg_temperature"))
    print("is_hot_day       :", insights.get("is_hot_day"))
    print("is_rainy_day     :", insights.get("is_rainy_day"))
    print("is_sunny_day     :", insights.get("is_sunny_day"))
    print("beach_score      :", insights.get("beach_score"))
    print("outdoor_score    :", insights.get("outdoor_score"))
    print("indoor_score     :", insights.get("indoor_score"))

    print("\n===== ERRORS =====\n")
    print(result.get("errors", []))


if __name__ == "__main__":
    main()
