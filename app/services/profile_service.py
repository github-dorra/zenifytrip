import requests
import httpx
from typing import Optional, Dict, Any
from app.config.settings import TRAVELLER_MANAGEMENT_API_URL, API_KEY


class ProfileService:

    @staticmethod
    async def get_traveller_profile(traveller_id: str) -> Optional[Dict[str, Any]]:
        if not traveller_id:
            return None

        url = f"{TRAVELLER_MANAGEMENT_API_URL}/{traveller_id}"
        headers = {
            "Authorization": f"Bearer {API_KEY}"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=30)
                response.raise_for_status()

            return response.json()

        except Exception as e:
            print(f"[ProfileService] Error: {e}")
            return None