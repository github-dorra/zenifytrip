import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MapService:
    """
    Geo service layer.

    Role:
    - provide user location fallback
    - later can integrate Google Maps / IP geolocation / profile memory
    """

    def __init__(self):
        # future: API keys (Google Maps, IPStack, etc.)
        pass

    async def get_user_location(self) -> Optional[Dict[str, Any]]:
        """
        Fallback location when user does not provide city/coords.

        In production:
        - Google Maps Geolocation API
        - IP-based geolocation
        - User profile saved location

        For now: static fallback (Tunisia - Tunis)
        """

        try:
            # MOCK fallback (safe for dev/testing)
            location = {
                "lat": 36.8065,   # Tunis latitude
                "lng": 10.1815,   # Tunis longitude
                "city": "Tunis",
                "country": "TN"
            }

            logger.info(f"MapService fallback location used: {location}")

            return location

        except Exception as e:
            logger.exception(f"MapService error: {e}")
            return None