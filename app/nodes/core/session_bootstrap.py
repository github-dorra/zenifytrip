import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any

from app.services.cache_service import cache
from app.graph.state import GraphState

from app.config.settings import (TRAVELLER_API_URL, API_KEY)


def get_traveller_id_by_userID(user_id: str):

    if not user_id:
        return None

    cached_travellerId = cache.get(f"travellerId:{user_id}")

    if cached_travellerId:
        return cached_travellerId

    try:
        response = requests.get(
            f"{TRAVELLER_API_URL}/{user_id}",
            headers={
                "Authorization": f"Bearer {API_KEY}"
            }
        )

        response.raise_for_status()

        data = response.json()

        travellerId = data.get("id")

        if travellerId:
            cache.set(
                f"travellerId:{user_id}",
                travellerId,
                ttl_seconds=86400
            )

        return travellerId

    except requests.RequestException as e:
        print(f"[BootstrapSession] Error: {e}")
        return None


def bootstrap_session(state: GraphState):

    user_id = state.get("user_id")

    # user_id absent = USER NATIF anonyme — cas normal (app sans compte)
    if not user_id:
        return {
            "travellerId":    None,
            "user_type":      "native",
            "suggestion_mode": "exploratory",
        }

    travellerId = state.get("travellerId")

    if not travellerId:
        travellerId = get_traveller_id_by_userID(user_id)

    if travellerId:
        user_type = "real"
        suggestion_mode = "precise_plan"
    else:
        user_type = "native"
        suggestion_mode = "exploratory"

    return {
        "travellerId": travellerId,
        "user_type": user_type,
        "suggestion_mode": suggestion_mode,
    }