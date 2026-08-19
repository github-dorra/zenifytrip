"""
InformationNode — pipeline informatif (travel_question / booking_question).
Node Python rule-based, 0 appel LLM.

Détecte le sous-type de la question et assemble les données pertinentes depuis
le state → écrit information_context pour informative_response_node (Agent 3).

Subtypes :
  follow_up_place  : où est quelque chose déjà recommandé → last_candidates
  weather          : météo destination → weather_context (live ou connaissance générale)
  booking_info     : infos réservation → availability_result + booking_anchors
  session_planning : résumé planifié → last_candidates / ranked_results
  dynamic_factual  : TOUTES les autres questions → Tavily Search d'abord,
                     fallback transparent Agent 3 (mémoire LLM) si Tavily absent/timeout.
                     Couvre : visa, horaires, prix, événements, attractions, culture, gastronomie...
"""
import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.config import settings as _s

_log = logging.getLogger(__name__)


# ── Vocabulaires de détection ────────────────────────────────────────────────

_PLACE_KW = frozenset({
    "où", "ou se", "comment aller", "adresse", "chemin", "trouver",
    "situe", "localisation", "direction", "maps", "gps", "plan",
    "emplacement", "accès", "acces", "y aller",
})

_WEATHER_KW = frozenset({
    # Météo directe
    "météo", "meteo", "temperature", "température",
    "quel temps", "temps qu'il fait", "temps fait-il", "fait-il",
    "chaud", "froid", "chaleur", "pluie", "pluvieux", "soleil", "vent",
    "nuageux", "beau temps", "climat", "weather",
    # Vêtements / préparation vestimentaire
    "vêtements", "vetements", "habits", "tenue", "imperméable", "impermeable",
    "manteau", "pull", "légèrement vêtu",
    # Baignade faisable (météo-dépendant) — "plage" seul retiré : trop ambigu
    # "meilleure plage à Sfax" = recommandation → dynamic_factual
    # "peut-on se baigner à la plage" = météo → couvert par "baigner"/"baignade"
    "baigner", "nager", "baignade", "se baigner", "natation",
    # Saison / période idéale
    "saison", "période idéale", "periode ideale",
    "meilleure période", "meilleure saison", "bonne période",
})

_BOOKING_KW = frozenset({
    "réservation", "reservation", "booking", "voucher",
    "chambre", "confirmé", "confirme", "mon hôtel", "mon hotel",
    "ma réservation", "billet", "check-in", "check in",
    # Vols — questions sur le vol personnel du voyageur
    "mon vol", "heure du vol", "heure de vol", "heure d'arrivée", "heure d'atterrissage",
    "décollage", "decolage", "atterrissage", "atterrisage",
    "vol aller", "vol retour", "numéro de vol", "numero de vol",
    "compagnie aérienne", "mon billet d'avion",
})

_PLANNING_KW = frozenset({
    "résume", "resume", "récapitule", "recapitule",
    "planifié", "planifie", "prévu", "prevu", "décidé",
    "qu'avons", "on a prévu", "notre plan", "programme",
    "récap", "recap",
})


# Cache session en mémoire — évite de rappeler Tavily pour la même question dans la même session
_TAVILY_SESSION_CACHE: Dict[str, Dict] = {}

_AVAIL_FIELDS = (
    "trip_is_ongoing", "hotel_name", "destination",
    "outbound_date", "return_date", "days_remaining",
)
_ANCHOR_FIELDS = (
    "meal_plan", "breakfast_included", "lunch_included",
    "dinner_included", "booked_services",
)


def _has(msg: str, keywords) -> bool:
    return any(kw in msg for kw in keywords)


def _profile_flights(profile_data: Optional[Dict]) -> Dict:
    """Retourne le dict flights normalisé depuis profile_data, ou {} si absent."""
    return (
        ((profile_data or {}).get("travel_preferences") or {})
        .get("flights") or {}
    )


def _detect_subtype(
    msg_lower: str,
    last_candidates: List[Dict],
    availability_result: Optional[Dict],
    booking_anchors: Optional[Dict],
    profile_data: Optional[Dict] = None,
) -> str:
    if _has(msg_lower, _PLACE_KW) and last_candidates:
        return "follow_up_place"
    if _has(msg_lower, _WEATHER_KW):
        return "weather"
    # booking_info si données dispo d'une des 3 sources :
    #   - API availability_checker (trip_is_ongoing, hotel_name...)
    #   - booking_anchors (meal_plan, booked_services...)
    #   - flights normalisés depuis profile_data (outbound/return)
    flights = _profile_flights(profile_data)
    has_booking_ctx = bool(
        availability_result
        or booking_anchors
        or flights.get("outbound")
        or ((profile_data or {}).get("travel_preferences") or {}).get("accommodation")
    )
    if _has(msg_lower, _BOOKING_KW) and has_booking_ctx:
        return "booking_info"
    if _has(msg_lower, _PLANNING_KW):
        return "session_planning"
    # Toute question non classifiée → Tavily d'abord (fallback Agent 3 si Tavily absent)
    # Aucune liste de mots-clés ne peut couvrir toutes les questions touristiques possibles.
    return "dynamic_factual"


def _resolve_follow_up_place(
    msg_lower: str,
    last_candidates: List[Dict],
) -> Tuple[Dict, float]:
    """Cherche le candidat par nom dans le message ; fallback = premier candidat."""
    for c in last_candidates:
        name_parts = (c.get("name") or "").lower().split()
        significant = [p for p in name_parts if len(p) > 3]
        if any(p in msg_lower for p in significant):
            return {"candidate": c, "match_type": "by_name"}, 0.85
    return {"candidate": last_candidates[0], "match_type": "implicit"}, 0.50


def _resolve_weather(
    weather_context: Optional[Dict],
    destination: Optional[str],
) -> Tuple[Dict, float]:
    if weather_context:
        insights = weather_context.get("insights") or {}
        return {
            "has_live_data": True,
            "destination": destination,
            "outdoor_score": insights.get("outdoor_score"),
            "indoor_score": insights.get("indoor_score"),
            "is_hot_day": insights.get("is_hot_day"),
            "summary": weather_context.get("summary"),
        }, 0.90
    return {"has_live_data": False, "destination": destination}, 0.60


def _fmt_flight_time(iso_str: str) -> str:
    """'2026-07-20T08:30:00.000Z' → '08:30' pour l'affichage."""
    try:
        t = iso_str.replace("Z", "").split("T")
        return t[1][:5] if len(t) > 1 else iso_str
    except Exception:
        return iso_str


def _extract_flight_info(flight: Dict) -> Dict:
    """
    Extrait les champs utiles d'un objet flight NORMALISÉ (profile_builder_service).
    Format normalisé : flight_number, from.name/iata, to.name/iata, takeoff_time, landing_time
    """
    if not flight:
        return {}
    info: Dict = {}
    if flight.get("flight_number"):
        info["flight_number"] = flight["flight_number"]
    if flight.get("airline"):
        info["airline"] = flight["airline"]
    if flight.get("takeoff_time"):
        info["takeoff_time"] = _fmt_flight_time(flight["takeoff_time"])
    if flight.get("landing_time"):
        info["landing_time"] = _fmt_flight_time(flight["landing_time"])
    dep = flight.get("from") or {}
    arr = flight.get("to")   or {}
    if dep.get("name") or dep.get("iata"):
        info["departure_airport"] = dep.get("name") or dep.get("iata")
    if arr.get("name") or arr.get("iata"):
        info["arrival_airport"] = arr.get("name") or arr.get("iata")
    return info


def _resolve_booking_info(
    availability_result: Optional[Dict],
    booking_anchors: Optional[Dict],
    profile_data: Optional[Dict] = None,
) -> Tuple[Dict, float]:
    data: Dict = {}
    if availability_result:
        data.update({k: availability_result[k] for k in _AVAIL_FIELDS if availability_result.get(k) is not None})
    if booking_anchors:
        data.update({k: booking_anchors[k] for k in _ANCHOR_FIELDS if booking_anchors.get(k) is not None})
    if profile_data:
        # Heures de vol depuis le profil normalisé (profile_data.travel_preferences.flights)
        flights = _profile_flights(profile_data)
        outbound = flights.get("outbound") or {}
        if outbound:
            info = _extract_flight_info(outbound)
            if info:
                data["outbound_flight"] = info
        return_fl = flights.get("return") or {}
        if return_fl:
            info = _extract_flight_info(return_fl)
            if info:
                data["return_flight"] = info
        # Nom de l'hôtel depuis accommodation normalisée si pas déjà dans availability_result
        if not data.get("hotel_name"):
            accom = (profile_data.get("travel_preferences") or {}).get("accommodation") or {}
            if accom.get("hotel_name"):
                data["hotel_name"] = accom["hotel_name"]
    return data, 0.85 if data else 0.30


def _resolve_dynamic_factual(
    msg_lower: str,
    original_message: str,
    destination: Optional[str],
) -> Tuple[Dict, float]:
    """
    Appelle Tavily Search pour les questions dynamiques (visa, prix, horaires, événements).
    Cache session → même question dans la même session ne déclenche pas deux appels.
    Fallback transparent (has_web_data=False) si clé absente, timeout ou 0 résultats.
    """
    cache_key = msg_lower.strip()
    if cache_key in _TAVILY_SESSION_CACHE:
        return _TAVILY_SESSION_CACHE[cache_key], 0.82

    api_key = getattr(_s, "TAVILY_API_KEY", "") or ""
    if not api_key:
        return {"has_web_data": False, "reason": "no_api_key"}, 0.55

    # Query enrichie : question + destination (si connue) + année courante
    year = datetime.datetime.now().year
    parts = [original_message.strip()]
    if destination:
        parts.append(destination)
    parts.append(str(year))
    query = " ".join(parts)

    timeout    = int(getattr(_s, "TAVILY_TIMEOUT_SECONDS", 5))
    max_results = int(getattr(_s, "TAVILY_MAX_RESULTS",    3))

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key":        api_key,
                "query":          query,
                "search_depth":   "basic",
                "max_results":    max_results,
                "include_answer": True,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []

        if not results:
            return {"has_web_data": False, "reason": "no_results"}, 0.55

        resolved = {
            "has_web_data": True,
            "query_used":   query,
            "answer":       data.get("answer"),  # réponse directe Tavily si disponible
            "sources": [
                {
                    "title":   r.get("title", ""),
                    "url":     r.get("url", ""),
                    "content": (r.get("content") or "")[:400],
                }
                for r in results[:max_results]
            ],
        }
        _TAVILY_SESSION_CACHE[cache_key] = resolved
        return resolved, 0.82

    except Exception as exc:
        _log.warning(f"[information_node] Tavily error: {exc}")
        return {"has_web_data": False, "reason": "tavily_error"}, 0.55


def _resolve_session_planning(
    last_candidates: List[Dict],
    ranked_results: List[Dict],
) -> Tuple[Dict, float]:
    items = last_candidates or ranked_results or []
    recommended = [
        {"name": c.get("name"), "type": c.get("activity_type") or c.get("type") or "?"}
        for c in items[:4]
    ]
    return {"recommended_items": recommended}, 0.70 if recommended else 0.30


class InformationNode(BaseNode):

    def __init__(self):
        super().__init__(NodeConfig(name="information_node"))

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        original_message = state.get("normalized_message") or state.get("user_message") or ""
        msg_lower = original_message.lower()

        last_candidates     = state.get("last_candidates") or []
        weather_context     = state.get("weather_context")
        availability_result = state.get("availability_result")
        booking_anchors     = state.get("booking_anchors")
        profile_data        = state.get("profile_data")
        ranked_results      = state.get("ranked_results") or []
        destination         = (state.get("merged_context") or {}).get("destination")

        subtype = _detect_subtype(
            msg_lower, last_candidates, availability_result, booking_anchors, profile_data
        )

        resolved_data: Optional[Dict] = None
        confidence: float = 0.5
        fallback_suggestion: Optional[str] = None

        if subtype == "follow_up_place":
            resolved_data, confidence = _resolve_follow_up_place(msg_lower, last_candidates)
            if confidence < 0.55:
                fallback_suggestion = "Pour l'adresse exacte, cherchez sur Google Maps."

        elif subtype == "weather":
            resolved_data, confidence = _resolve_weather(weather_context, destination)

        elif subtype == "booking_info":
            resolved_data, confidence = _resolve_booking_info(
                availability_result, booking_anchors, profile_data
            )

        elif subtype == "session_planning":
            resolved_data, confidence = _resolve_session_planning(last_candidates, ranked_results)

        elif subtype == "dynamic_factual":
            resolved_data, confidence = _resolve_dynamic_factual(
                msg_lower, original_message, destination
            )
            if not (resolved_data or {}).get("has_web_data"):
                fallback_suggestion = (
                    "Cette information peut avoir changé. "
                    "Je vous recommande de vérifier sur le site officiel."
                )

        # factual → resolved_data = None, LLM répond avec sa connaissance générale (stable)

        return {
            "information_context": {
                "subtype": subtype,
                "resolved_data": resolved_data,
                "confidence": round(confidence, 2),
                "fallback_suggestion": fallback_suggestion,
            }
        }
