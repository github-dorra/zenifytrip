from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


# ── Ranking ───────────────────────────────────────────────────────────────────

class RankingScore(BaseModel):
    """Score produit par le LLM pour un candidat. Mergé avec le candidat original en Python."""

    id:                    str   = ""
    rank:                  int   = 0
    user_score:            float = 0.0   # pertinence utilisateur
    business_score:        float = 0.0   # priorité commerciale agence
    final_score:           float = 0.0   # 0.7*user + 0.3*business
    recommendation_reason: str   = ""    # phrase FR naturelle — générée par le LLM

    @field_validator("user_score", "business_score", "final_score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 4)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("rank", mode="before")
    @classmethod
    def clean_rank(cls, v):
        try:
            return max(0, int(v or 0))
        except (ValueError, TypeError):
            return 0

    @field_validator("id", "recommendation_reason", mode="before")
    @classmethod
    def clean_str(cls, v):
        return str(v).strip() if v else ""


class RankingOutput(BaseModel):
    """Sortie brute du ranking_node — liste des scores LLM avant merge avec candidats."""

    scores:     List[RankingScore] = Field(default_factory=list)
    confidence: float              = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 3)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("scores", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        return list(v)


# ── Day Planner ───────────────────────────────────────────────────────────────

class ItinerarySlot(BaseModel):
    """Un créneau horaire dans une journée d'itinéraire."""

    time_of_day:  str           = "morning"   # morning | afternoon | evening | night
    type:         str           = "activity"   # activity | restaurant | hotel | transport
    name:         str           = ""
    location:     Optional[str] = None
    duration_min: Optional[int] = None
    notes:        Optional[str] = None
    candidate_id: Optional[str] = None        # lien vers le candidat source dans ranked_results

    @field_validator("duration_min", mode="before")
    @classmethod
    def clean_int(cls, v):
        if v is None:
            return None
        try:
            return max(0, int(v))
        except (ValueError, TypeError):
            return None

    @field_validator("time_of_day", mode="before")
    @classmethod
    def normalize_time(cls, v):
        valid = {"morning", "afternoon", "evening", "night"}
        s = str(v).strip().lower() if v else "morning"
        return s if s in valid else "morning"

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v):
        valid = {"activity", "restaurant", "hotel", "transport"}
        s = str(v).strip().lower() if v else "activity"
        return s if s in valid else "activity"


class ItineraryDay(BaseModel):
    """Une journée dans l'itinéraire complet."""

    day:   int                 = 1
    theme: str                 = ""
    slots: List[ItinerarySlot] = Field(default_factory=list)
    notes: Optional[str]       = None

    @field_validator("day", mode="before")
    @classmethod
    def clean_day(cls, v):
        try:
            return max(1, int(v or 1))
        except (ValueError, TypeError):
            return 1

    @field_validator("slots", mode="before")
    @classmethod
    def ensure_slots(cls, v):
        if v is None:
            return []
        return list(v)


class Itinerary(BaseModel):
    """Itinéraire complet produit par day_planner_node."""

    destination:      str              = ""
    duration_days:    int              = 0
    days:             List[ItineraryDay] = Field(default_factory=list)
    total_activities: int              = 0
    confidence:       float            = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 3)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("days", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        return list(v)

    @field_validator("duration_days", "total_activities", mode="before")
    @classmethod
    def clean_int(cls, v):
        try:
            return max(0, int(v or 0))
        except (ValueError, TypeError):
            return 0
