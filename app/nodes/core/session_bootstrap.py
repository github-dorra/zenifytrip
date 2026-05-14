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

    cached_traveller_id = cache.get(f"traveller_id:{user_id}")

    if cached_traveller_id:
        return cached_traveller_id

    try:
        response = requests.get(
            f"{TRAVELLER_API_URL}/{user_id}",
            headers={
                "Authorization": f"Bearer {API_KEY}"
            }
        )

        response.raise_for_status()

        data = response.json()

        traveller_id = data.get("traveller_id")

        if traveller_id:
            cache.set(
                f"traveller_id:{user_id}",
                traveller_id,
                ttl_seconds=86400
            )

        return traveller_id

    except requests.RequestException as e:
        print(f"[BootstrapSession] Error: {e}")
        return None


def bootstrap_session(state: GraphState):

    user_id = state.get("user_id")

    if not user_id:
        state.setdefault("errors", []).append("Missing user_id")
        return state

    traveller_id = state.get("traveller_id")

    if not traveller_id:

        traveller_id = get_traveller_id_by_userID(user_id)

        state["traveller_id"] = traveller_id

    state["is_authenticated"] = True

    return state