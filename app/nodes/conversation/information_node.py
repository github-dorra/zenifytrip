"""
InformationNode — pipeline informatif (travel_question / booking_question).
Node Python rule-based, 0 appel LLM.

Détecte le sous-type de la question et assemble les données pertinentes depuis
le state → écrit information_context pour final_response_node.

Subtypes :
  follow_up_place  : où est quelque chose déjà recommandé → last_candidates
  weather          : météo destination → weather_context (live ou connaissance générale)
  booking_info     : infos réservation → availability_result + booking_anchors
  session_planning : résumé planifié → last_candidates / ranked_results
  factual          : question générale Tunisie → LLM répond seul (resolved_data=None)
"""
from typing import Any, Dict, List, Optional, Tuple

from app.nodes.core.Base_node import BaseNode, NodeConfig


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
    # Baignade / plage faisable
    "baigner", "nager", "baignade", "se baigner", "plage", "natation",
    # Saison / période idéale
    "saison", "période idéale", "periode ideale",
    "meilleure période", "meilleure saison", "bonne période",
})

_BOOKING_KW = frozenset({
    "réservation", "reservation", "booking", "voucher",
    "chambre", "confirmé", "confirme", "mon hôtel", "mon hotel",
    "ma réservation", "billet", "check-in", "check in",
})

_PLANNING_KW = frozenset({
    "résume", "resume", "récapitule", "recapitule",
    "planifié", "planifie", "prévu", "prevu", "décidé",
    "qu'avons", "on a prévu", "notre plan", "programme",
    "récap", "recap",
})

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


def _detect_subtype(
    msg_lower: str,
    last_candidates: List[Dict],
    availability_result: Optional[Dict],
    booking_anchors: Optional[Dict],
) -> str:
    if _has(msg_lower, _PLACE_KW) and last_candidates:
        return "follow_up_place"
    if _has(msg_lower, _WEATHER_KW):
        return "weather"
    if _has(msg_lower, _BOOKING_KW) and (availability_result or booking_anchors):
        return "booking_info"
    if _has(msg_lower, _PLANNING_KW):
        return "session_planning"
    return "factual"


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


def _resolve_booking_info(
    availability_result: Optional[Dict],
    booking_anchors: Optional[Dict],
) -> Tuple[Dict, float]:
    data: Dict = {}
    if availability_result:
        data.update({k: availability_result[k] for k in _AVAIL_FIELDS if availability_result.get(k) is not None})
    if booking_anchors:
        data.update({k: booking_anchors[k] for k in _ANCHOR_FIELDS if booking_anchors.get(k) is not None})
    return data, 0.80 if data else 0.30


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
        msg_lower = (
            state.get("normalized_message") or state.get("user_message") or ""
        ).lower()

        last_candidates     = state.get("last_candidates") or []
        weather_context     = state.get("weather_context")
        availability_result = state.get("availability_result")
        booking_anchors     = state.get("booking_anchors")
        ranked_results      = state.get("ranked_results") or []
        destination         = (state.get("merged_context") or {}).get("destination")

        subtype = _detect_subtype(
            msg_lower, last_candidates, availability_result, booking_anchors
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
            resolved_data, confidence = _resolve_booking_info(availability_result, booking_anchors)

        elif subtype == "session_planning":
            resolved_data, confidence = _resolve_session_planning(last_candidates, ranked_results)

        # factual → resolved_data = None, LLM répond avec sa connaissance générale

        return {
            "information_context": {
                "subtype": subtype,
                "resolved_data": resolved_data,
                "confidence": round(confidence, 2),
                "fallback_suggestion": fallback_suggestion,
            }
        }
