from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Optional


class AirportInfo(BaseModel):
    name: Optional[str] = None
    iata_code: Optional[str] = None
    icao_code: Optional[str] = None

    @field_validator("name", "iata_code", "icao_code", mode="before")
    @classmethod
    def clean_str(cls, v):
        if v is None:
            return None
        return str(v).strip() or None


class AirlineInfo(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def clean_str(cls, v):
        if v is None:
            return None
        return str(v).strip() or None


class FlightCandidate(BaseModel):
    id: str
    flight_number: Optional[str] = None
    normalized_number: Optional[str] = None

    # Type de leg : "outbound" | "return" — depuis le champ "type" de l'API
    # (ce champ indique la direction, pas le nombre d'escales)
    flight_type: Optional[str] = None
    has_layover: bool = False
    layover_count: int = 0

    # Tier de recommandation : "profile" (USER RÉEL) | "catalogue" (API vols)
    tier: Optional[str] = None

    # Durée
    duration_minutes: Optional[int] = None
    duration_hours: Optional[float] = None

    # Horaires
    takeoff_time: Optional[str] = None
    landing_time: Optional[str] = None

    # Aéroports
    takeoff_airport: Optional[AirportInfo] = None
    landing_airport: Optional[AirportInfo] = None

    # Compagnie
    airline: Optional[AirlineInfo] = None

    # Score de correspondance contraintes user (0-1) — calculé par flight_node
    match_score: float = 0.0

    # Critères satisfaits — pour que ranking_node sache ce qui matche
    matched_criteria: List[str] = Field(default_factory=list)

    # ── Enrichissement destination (tunisia_destinations.py) ──────
    # Destination réelle demandée par le user (peut différer de l'aéroport)
    user_destination: Optional[str] = None

    # Transfert nécessaire si destination ≠ ville de l'aéroport
    transfer_needed: bool = False
    transfer_distance_km: Optional[int] = None
    transfer_label: Optional[str] = None   # ex: "Monastir" pour Kairouan

    # Features brutes pour ranking_node (tags, vibe, traveler_types, saisons)
    destination_features: Optional[Dict[str, Any]] = None

    # Conseil saisonnier : {"recommended": bool, "reason": str}
    seasonal_advice: Optional[Dict[str, Any]] = None

    # Phrase de recommandation prête pour final_response
    recommendation_reason: Optional[str] = None

    @field_validator("match_score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        return max(0.0, min(float(v or 0), 1.0))

    @field_validator("duration_hours", mode="before")
    @classmethod
    def round_hours(cls, v):
        if v is None:
            return None
        return round(float(v), 2)

    @field_validator("matched_criteria", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("flight_type", mode="before")
    @classmethod
    def normalize_type(cls, v):
        if v is None:
            return None
        return str(v).strip().lower()  # conserve la valeur brute de l'API (outbound/return/direct/connecting)


class FlightNodeOutput(BaseModel):
    flight_candidates: List[FlightCandidate] = Field(default_factory=list)
    total_found: int = 0
    filters_applied: List[str] = Field(default_factory=list)
    confidence: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v):
        return max(0.0, min(float(v or 0), 1.0))

    @field_validator("flight_candidates", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        return v
