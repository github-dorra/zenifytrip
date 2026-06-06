import requests
from typing import Optional, Dict, Any, List
from app.config.settings import FLIGHTS_API_URL, AIRPORTS_API_URL, AIRLINES_API_URL, API_KEY
from app.services.cache_service import cache, SimpleTTLCache
from app.data.tunisia_destinations import (
    city_to_airports,
    destination_features,
    get_seasonal_advice,
    get_recommendation_reason,
)


class FlightService:

    HEADERS = {"Authorization": f"Bearer {API_KEY}"}
    TIMEOUT = 30

    # ------------------------------------------------------------------
    # Fetch brut depuis l'API (avec cache centralisé)
    # ------------------------------------------------------------------

    @staticmethod
    def get_flights(take: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
        """Retourne tous les vols depuis l'API — mis en cache 6h."""
        cache_key = f"flights_all_{take}_{skip}"
        return cache.get_or_set(
            cache_key,
            lambda: FlightService._fetch_flights(take, skip),
            SimpleTTLCache.TTL_FLIGHTS,
        )

    @staticmethod
    def _fetch_flights(take: int, skip: int) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                FLIGHTS_API_URL,
                headers=FlightService.HEADERS,
                params={"take": take, "skip": skip},
                timeout=FlightService.TIMEOUT,
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            print(f"[FlightService] _fetch_flights error: {e}")
            return []

    @staticmethod
    def get_flight_by_id(flight_id: str) -> Optional[Dict[str, Any]]:
        """Retourne le détail d'un vol — mis en cache 6h."""
        cache_key = f"flights_detail_{flight_id}"
        return cache.get_or_set(
            cache_key,
            lambda: FlightService._fetch_flight_by_id(flight_id),
            SimpleTTLCache.TTL_FLIGHTS,
        )

    @staticmethod
    def _fetch_flight_by_id(flight_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{FLIGHTS_API_URL}/{flight_id}",
                headers=FlightService.HEADERS,
                timeout=FlightService.TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[FlightService] _fetch_flight_by_id error: {e}")
            return None

    @staticmethod
    def get_airports() -> List[Dict[str, Any]]:
        """Retourne les aéroports — mis en cache 24h."""
        return cache.get_or_set(
            "airports_all",
            FlightService._fetch_airports,
            SimpleTTLCache.TTL_AIRPORTS,
        )

    @staticmethod
    def _fetch_airports() -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                AIRPORTS_API_URL,
                headers=FlightService.HEADERS,
                timeout=FlightService.TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else data.get("results", [])
        except Exception as e:
            print(f"[FlightService] _fetch_airports error: {e}")
            return []

    @staticmethod
    def get_airlines() -> List[Dict[str, Any]]:
        """Retourne les compagnies aériennes — mis en cache 24h."""
        return cache.get_or_set(
            "airlines_all",
            FlightService._fetch_airlines,
            SimpleTTLCache.TTL_AIRLINES,
        )

    @staticmethod
    def _fetch_airlines() -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                AIRLINES_API_URL,
                headers=FlightService.HEADERS,
                timeout=FlightService.TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else data.get("results", [])
        except Exception as e:
            print(f"[FlightService] _fetch_airlines error: {e}")
            return []

    # ------------------------------------------------------------------
    # Helpers destination
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_travel_month(constraints: Dict[str, Any]) -> Optional[int]:
        """Extrait le mois de voyage depuis start_date (format YYYY-MM-DD ou DD/MM/YYYY)."""
        start_date = (constraints.get("start_date") or "").strip()
        if not start_date:
            return None
        try:
            if "-" in start_date:
                parts = start_date.split("-")
                return int(parts[1]) if len(parts) >= 2 else None
            if "/" in start_date:
                parts = start_date.split("/")
                if len(parts[0]) == 4:      # YYYY/MM/DD
                    return int(parts[1])
                return int(parts[1])         # DD/MM/YYYY
        except Exception:
            return None

    @staticmethod
    def _enrich_with_destination(
        candidate: Dict[str, Any],
        user_destination: str,
        airport_info: Dict[str, Any],
        travel_month: Optional[int],
    ) -> Dict[str, Any]:
        """
        Enrichit un candidat vol avec les données de tunisia_destinations :
        - destination réelle du user
        - transfert nécessaire + distance
        - features destination pour ranking_node
        - conseil saisonnier
        - phrase de recommandation
        """
        iata         = airport_info.get("iata") or ""
        distance_km  = airport_info.get("distance_km")
        transfer_needed = bool(distance_km and distance_km > 15)

        features = destination_features(iata) if iata else {}
        advice   = get_seasonal_advice(iata, travel_month) if (iata and travel_month) else {}
        reason   = get_recommendation_reason(iata, travel_month) if (iata and travel_month) else ""

        candidate.update({
            "user_destination":      user_destination or None,
            "transfer_needed":       transfer_needed,
            "transfer_distance_km":  distance_km,
            "transfer_label":        airport_info.get("label"),
            "destination_features":  features or None,
            "seasonal_advice":       advice or None,
            "recommendation_reason": reason or None,
        })
        return candidate

    # ------------------------------------------------------------------
    # Filtrage
    # ------------------------------------------------------------------

    @staticmethod
    def filter_flights(
        flights: List[Dict[str, Any]],
        constraints: Dict[str, Any],
        target_iata: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Filtre les vols selon les contraintes extraites du merged_context.
        Si target_iata est fourni → matching exact sur landing_airport.iataCode.
        Sinon → matching textuel sur destination.
        """
        origin = (constraints.get("origin") or "").strip().lower()
        flight_pref   = (constraints.get("flight_preferences") or {})
        preferred_type = (flight_pref.get("flight_type") or "").strip().lower()

        # Destination : IATA exact (priorité) ou texte brut (fallback)
        dest_iata = (target_iata or "").strip().upper()
        dest_text = (constraints.get("destination") or "").strip().lower()

        filtered = []

        for flight in flights:
            criteria = []

            landing      = flight.get("landingAirport") or {}
            takeoff      = flight.get("takeoffAirport") or {}
            landing_iata = (landing.get("iataCode") or "").upper()
            landing_name = (landing.get("name") or "").lower()
            takeoff_name = (takeoff.get("name") or "").lower()
            takeoff_iata = (takeoff.get("iataCode") or "").lower()
            flight_type  = (flight.get("type") or "").lower()

            # Destination — matching IATA exact si disponible, sinon texte
            if dest_iata:
                if landing_iata == dest_iata:
                    criteria.append("destination")
                else:
                    continue
            elif dest_text:
                if dest_text in landing_name or dest_text in landing_iata.lower():
                    criteria.append("destination")
                else:
                    continue

            # Origine
            if origin:
                if origin in takeoff_name or origin in takeoff_iata:
                    criteria.append("origin")

            # Type de vol
            if preferred_type:
                if preferred_type in ("direct", "nonstop") and flight_type in ("direct", "nonstop"):
                    criteria.append("direct_flight")
                elif preferred_type in ("connecting", "layover") and flight_type in ("connecting", "connection"):
                    criteria.append("connecting_flight")
            elif flight_type in ("direct", "nonstop"):
                criteria.append("direct_flight")

            # Durée raisonnable (< 12h)
            air_time = flight.get("airTime") or 0
            if 0 < air_time <= 720:
                criteria.append("reasonable_duration")

            flight["_matched_criteria"] = criteria
            filtered.append(flight)

        return filtered

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score_flight(flight: Dict[str, Any], constraints: Dict[str, Any]) -> float:
        """
        Calcule un match_score (0–1) basé sur les critères satisfaits.

        Poids :
          destination match   → 0.40
          origin match        → 0.20
          direct flight       → 0.20
          reasonable_duration → 0.10
          connecting_flight   → 0.05
        """
        criteria = flight.get("_matched_criteria", [])
        score = 0.0

        weights = {
            "destination": 0.40,
            "origin": 0.20,
            "direct_flight": 0.20,
            "reasonable_duration": 0.10,
            "connecting_flight": 0.05,
        }

        for c in criteria:
            score += weights.get(c, 0.0)

        # Aucune contrainte spécifiée → score de base 0.5
        destination = (constraints.get("destination") or "").strip()
        if not destination and not criteria:
            score = 0.50

        return round(min(score, 1.0), 4)

    # ------------------------------------------------------------------
    # Enrichissement compagnie
    # ------------------------------------------------------------------

    @staticmethod
    def build_airline_index(airlines: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Construit un index {airline_id: airline_data} pour enrichissement rapide."""
        index = {}
        for airline in airlines:
            aid = str(airline.get("id") or "")
            if aid:
                index[aid] = airline
        return index

    # ------------------------------------------------------------------
    # TIER 1 — Vols depuis le profil voyageur (USER RÉEL)
    # 0 appel API — données déjà dans le state via profile_data
    # ------------------------------------------------------------------

    @staticmethod
    def get_profile_flights(
        profile_data: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Extrait les vols aller + retour depuis le profil voyageur (USER RÉEL).
        Retourne [] si profile_data est vide ou si les vols ne matchent pas
        la destination demandée.
        """
        if not profile_data:
            return []

        destination = (constraints.get("destination") or "").strip().lower()
        candidates = []

        for key, label in [("outboundFlight", "aller"), ("returnFlight", "retour")]:
            flight = profile_data.get(key)
            if not flight:
                continue

            landing = flight.get("landingAirport") or {}
            landing_name = (landing.get("name") or "").lower()
            landing_iata = (landing.get("iataCode") or "").lower()

            # Si destination précisée, vérifier que le vol matche
            if destination and destination not in landing_name and destination not in landing_iata:
                continue

            air_time = flight.get("airTime") or 0
            criteria = ["profile_match"]
            if destination and (destination in landing_name or destination in landing_iata):
                criteria.append("destination")

            candidates.append({
                "id": f"profile_{key}",
                "flight_number": flight.get("flightNumber"),
                "normalized_number": None,
                "flight_type": "direct",
                "has_layover": False,
                "layover_count": 0,
                "duration_minutes": air_time,
                "duration_hours": round(air_time / 60, 2) if air_time else None,
                "takeoff_time": flight.get("takeoffTime"),
                "landing_time": flight.get("landingTime"),
                "takeoff_airport": {
                    "name": (flight.get("takeoffAirport") or {}).get("name"),
                    "iata_code": (flight.get("takeoffAirport") or {}).get("iataCode"),
                    "icao_code": None,
                },
                "landing_airport": {
                    "name": landing.get("name"),
                    "iata_code": landing.get("iataCode"),
                    "icao_code": None,
                },
                "airline": {"id": None, "name": None},
                "match_score": 1.0,        # vol du voyageur = priorité maximale
                "matched_criteria": criteria,
                "tier": "profile",
                "leg": label,
            })

        return candidates

    # ------------------------------------------------------------------
    # TIER 2 — Catalogue /api/flights (USER NATIF ou Tier 1 insuffisant)
    # ------------------------------------------------------------------

    @staticmethod
    def get_catalogue_flights(
        constraints: Dict[str, Any],
        max_candidates: int = 10,
        target_iata: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetche le catalogue complet depuis l'API (272 vols, mis en cache 6h).
        Filtre + score + enrichit avec compagnies.
        target_iata : si fourni, matching exact sur landing_airport.iataCode.
        """
        flights = FlightService.get_flights()
        airlines = FlightService.get_airlines()
        airline_index = FlightService.build_airline_index(airlines)

        filtered = FlightService.filter_flights(flights, constraints, target_iata=target_iata)

        candidates = []
        for flight in filtered:
            score = FlightService.score_flight(flight, constraints)
            criteria = flight.pop("_matched_criteria", [])

            air_time = flight.get("airTime") or 0
            flight_type_raw = (flight.get("type") or "").lower()
            # L'API retourne "outbound"/"return" (direction), pas "direct"/"connecting"
            # has_layover = True seulement si le type indique explicitement une connexion
            has_layover = flight_type_raw in ("connecting", "connection", "layover", "transit")

            airline_id = str(flight.get("airlineCompanyId") or "")
            airline_data = airline_index.get(airline_id, {})

            candidates.append({
                "id": str(flight.get("id") or ""),
                "flight_number": flight.get("flightNumber"),
                "normalized_number": flight.get("normalizedNumber"),
                "flight_type": flight_type_raw,
                "has_layover": has_layover,
                "layover_count": 0 if not has_layover else 1,
                "duration_minutes": air_time,
                "duration_hours": round(air_time / 60, 2) if air_time else None,
                "takeoff_time": flight.get("takeoffTime"),
                "landing_time": flight.get("landingTime"),
                "takeoff_airport": {
                    "name": (flight.get("takeoffAirport") or {}).get("name"),
                    "iata_code": (flight.get("takeoffAirport") or {}).get("iataCode"),
                    "icao_code": (flight.get("takeoffAirport") or {}).get("icaoCode"),
                },
                "landing_airport": {
                    "name": (flight.get("landingAirport") or {}).get("name"),
                    "iata_code": (flight.get("landingAirport") or {}).get("iataCode"),
                    "icao_code": (flight.get("landingAirport") or {}).get("icaoCode"),
                },
                "airline": {
                    "id": airline_id or None,
                    "name": airline_data.get("name"),
                },
                "match_score": score,
                "matched_criteria": criteria,
                "tier": "catalogue",
            })

        candidates.sort(key=lambda x: x["match_score"], reverse=True)
        return candidates[:max_candidates]

    # ------------------------------------------------------------------
    # Point d'entrée principal — Tier 1 → Tier 2
    # ------------------------------------------------------------------

    @staticmethod
    def get_flight_candidates(
        constraints: Dict[str, Any],
        profile_data: Optional[Dict[str, Any]] = None,
        max_candidates: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Pipeline Tier 1 / Tier 2 avec enrichissement destination :

        Tier 1 : vols du profil voyageur (0 appel API) — USER RÉEL
        Tier 2 : catalogue /api/flights vers chaque aéroport résolu
                 via city_to_airports(destination)

        Chaque candidat est enrichi avec :
          user_destination, transfer_needed, transfer_distance_km,
          destination_features, seasonal_advice, recommendation_reason
        """
        user_destination = (constraints.get("destination") or "").strip().lower()
        travel_month     = FlightService._extract_travel_month(constraints)

        # ── TIER 1 — profil voyageur ──────────────────────────────
        tier1_raw = FlightService.get_profile_flights(profile_data or {}, constraints)
        tier1 = []
        for c in tier1_raw:
            landing_iata = (c.get("landing_airport") or {}).get("iata_code") or ""
            airport_info = {
                "iata":        landing_iata.upper(),
                "distance_km": 0,
                "label":       (c.get("landing_airport") or {}).get("name"),
            }
            FlightService._enrich_with_destination(c, user_destination, airport_info, travel_month)
            tier1.append(c)

        if len(tier1) >= 2:
            return tier1[:max_candidates]

        # ── TIER 2 — catalogue multi-aéroports ───────────────────
        seen_ids = {c["id"] for c in tier1}
        tier2    = []

        if not user_destination:
            # Mode exploratory : pas de destination → on retourne tous les vols
            candidates = FlightService.get_catalogue_flights(
                constraints=constraints,
                max_candidates=max_candidates,
            )
            for c in candidates:
                if c["id"] not in seen_ids:
                    FlightService._enrich_with_destination(
                        c, "", {"iata": None, "distance_km": None, "label": None}, travel_month
                    )
                    tier2.append(c)
                    seen_ids.add(c["id"])
        else:
            # Résoudre destination → liste d'aéroports ordonnés par distance
            target_airports = city_to_airports(user_destination)

            # Fallback : ville inconnue → cherche par texte brut dans l'API
            if not target_airports:
                target_airports = [{"iata": None, "distance_km": None, "label": None}]

            for airport_info in target_airports:
                iata = airport_info.get("iata")
                candidates = FlightService.get_catalogue_flights(
                    constraints=constraints,
                    max_candidates=max_candidates,
                    target_iata=iata,
                )
                for c in candidates:
                    if c["id"] not in seen_ids:
                        FlightService._enrich_with_destination(
                            c, user_destination, airport_info, travel_month
                        )
                        tier2.append(c)
                        seen_ids.add(c["id"])

        tier2.sort(key=lambda x: x["match_score"], reverse=True)
        slots    = max_candidates - len(tier1)
        combined = tier1 + tier2[:slots]
        return combined[:max_candidates]
