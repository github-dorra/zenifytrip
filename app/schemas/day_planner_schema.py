"""
app/schemas/day_planner_schema.py
Schéma Pydantic v2 — DayPlannerNode
Contrat de données entre ranking_node → day_planner_node → recommendation_response_node
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TimeSlot(str, Enum):
    MORNING   = "morning"
    AFTERNOON = "afternoon"
    EVENING   = "evening"


class ActivityType(str, Enum):
    HOTEL      = "hotel"
    RESTAURANT = "restaurant"
    ACTIVITY   = "activity"
    FLIGHT     = "flight"
    FREE       = "free"          # créneau libre suggéré


# ---------------------------------------------------------------------------
# Modèles atomiques
# ---------------------------------------------------------------------------

class DaySlotItem(BaseModel):
    """Un créneau dans la journée."""

    time_slot:   TimeSlot           = Field(...,  description="Moment de la journée")
    item_type:   ActivityType       = Field(...,  description="Type de l'élément")
    name:        str                = Field(...,  description="Nom du lieu / activité")
    location:    Optional[str]      = Field(None, description="Adresse ou ville")
    duration_minutes: Optional[int] = Field(None, description="Durée estimée en minutes")
    price_level: Optional[str]      = Field(None, description="Budget estimé : free | low | medium | high")
    notes:       Optional[str]      = Field(None, description="Conseil pratique ou remarque contextuelle")

    # Champs optionnels pour lien avec les candidats ranqués
    candidate_id:  Optional[str]   = Field(None, description="ID du candidat ranked_results d'origine")
    ranked_score:  Optional[float] = Field(None, description="Score issu du ranking_node")

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def clamp_duration(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        try:
            val = int(v)
            return max(15, min(val, 480))   # entre 15 min et 8h
        except (TypeError, ValueError):
            return None

    @field_validator("ranked_score", mode="before")
    @classmethod
    def clamp_score(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return max(0.0, min(float(v), 1.0))
        except (TypeError, ValueError):
            return None


class DayItinerary(BaseModel):
    """Un jour complet dans l'itinéraire."""

    day_number: int                = Field(...,  description="Numéro du jour (1, 2, 3...)")
    date:       Optional[str]      = Field(None, description="Date ISO si connue (ex: 2026-07-14)")
    title:      Optional[str]      = Field(None, description="Titre évocateur du jour (ex: 'Découverte de la médina')")
    slots:      List[DaySlotItem]  = Field(default_factory=list, description="Créneaux ordonnés de la journée")
    day_notes:  Optional[str]      = Field(None, description="Notes globales sur la journée (météo, conseil transport...)")

    @field_validator("day_number", mode="before")
    @classmethod
    def ensure_positive(cls, v: Any) -> int:
        try:
            val = int(v)
            return max(1, val)
        except (TypeError, ValueError):
            return 1


# ---------------------------------------------------------------------------
# Output principal du node
# ---------------------------------------------------------------------------

class DayPlannerOutput(BaseModel):
    """
    Sortie complète du DayPlannerNode.
    Stockée dans GraphState.itinerary (via .model_dump()).
    """

    destination:   str                  = Field(...,        description="Destination principale")
    duration_days: int                  = Field(1,          description="Nombre de jours planifiés")
    days:          List[DayItinerary]   = Field(default_factory=list, description="Jours de l'itinéraire")

    # Notes transversales
    weather_note:  Optional[str]        = Field(None, description="Conseil météo global pour la période")
    budget_note:   Optional[str]        = Field(None, description="Estimation budget total")
    travel_tips:   Optional[List[str]]  = Field(None, description="Conseils pratiques généraux (transport, langue, horaires)")

    # Méta
    confidence:    float                = Field(0.0,  description="Confiance du LLM dans l'itinéraire généré")
    generated_by:  str                  = Field("day_planner_node", description="Identifiant du node producteur")

    @field_validator("duration_days", mode="before")
    @classmethod
    def clamp_days(cls, v: Any) -> int:
        try:
            val = int(v)
            return max(1, min(val, 30))   # 1 à 30 jours
        except (TypeError, ValueError):
            return 1

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            return max(0.0, min(float(v or 0), 1.0))
        except (TypeError, ValueError):
            return 0.0