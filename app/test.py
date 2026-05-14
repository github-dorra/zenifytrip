from app.nodes.recommendation.context.semantic_node import SemanticAgentNode


def main():

    node = SemanticAgentNode()

    state = {
        "user_message": (
            "recommande a moi des activities a faire demain. "

        ),

        "merged_context": {
            "primary_intent": "activity_recommendation",
            "secondary_intents": [],

            "destination": "monastir",
            "travelers": 4,
            "is_family": True,
            "duration_days": 5,
            "budget_level": "low",

            "interests": [
                "beach",
                "water",
                "kids"
            ]
        },

        "weather_context": {
            "insights": {
                "avg_temperature": 31,
                "is_hot_day": True,
                "is_rainy_day": False,
                "is_sunny_day": True,

                "beach_score": 0.95,
                "outdoor_score": 0.90,
                "indoor_score": 0.20,

                "recommendation_hint": "beach"
            }
        }
    }

    result = node.run(state)

    print("\n================ RESULT ================\n")

    for key, value in result.items():
        print(f"{key}:")
        print(value)
        print()


if __name__ == "__main__":
    main()