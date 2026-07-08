from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class ActivityCandidate(BaseModel):

    # ── Identification ────────────────────────────────────────────────
    id:                str
    name:              str
    description:       Optional[str] = None

    # ── Catégorie sémantique ──────────────────────────────────────────
    activity_type: str = "unknown"  # culture|nature|adventure|relax|city_experience|unknown

    # ── Provenance ────────────────────────────────────────────────────
    source:            str = "internal"   # "internal" | "mongodb"
    tier:              str = "agency"     # "agency" | "external"
    activity_id:       str = ""
    booking_reference: str = ""
    hotel_name:        Optional[str] = None

    # ── Géographie ───────────────────────────────────────────────────
    destination:          str           = ""
    zone:                 Optional[str] = None
    has_geospatial_info:  bool          = False
    distance_km:          Optional[float] = None
    travel_time_min:      Optional[int]   = None

    # ── Dates ─────────────────────────────────────────────────────────
    date:              Optional[str] = None
    recurrence_start:  Optional[str] = None
    recurrence_end:    Optional[str] = None
    recurrence_days:   List[str] = Field(default_factory=list)

    # ── Tarifs ────────────────────────────────────────────────────────
    adult_price:   float = 0.0
    child_price:   float = 0.0
    baby_price:    float = 0.0
    currency:      str   = "TND"
    duration_hours: Optional[float] = None

    # ── Disponibilité ─────────────────────────────────────────────────
    max_participants:         int           = 0
    registered_participants:  int           = 0
    available_spots:          Optional[int] = None
    is_available:             Optional[bool] = None   # True=confirmé | False=indispo | None=inconnu (SOURCE 2)
    already_booked:           bool          = False

    # ── Avis (source MongoDB/TripAdvisor) ────────────────────────────
    rating:        Optional[float] = None
    reviews_count: Optional[int]   = None

    # ── Scoring — aligné sur hotel_schema (score / business_score / user_score) ──
    score:          float = 0.0
    business_score: float = 0.0
    user_score:     float = 0.0

    # ── Tags sémantiques + contexte ──────────────────────────────────
    semantic_tags:          List[str]     = Field(default_factory=list)
    recommendation_context: Optional[str] = None

    # ── Critères satisfaits — pour le ranking_node ────────────────────
    matched_criteria:      List[str]     = Field(default_factory=list)
    recommendation_reason: Optional[str] = None

    # =========================================================
    # VALIDATORS — normalise au lieu de crasher le pipeline
    # =========================================================

    @field_validator("score", "business_score", "user_score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 4)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("adult_price", "child_price", "baby_price", mode="before")
    @classmethod
    def clean_price(cls, v):
        try:
            return round(max(0.0, float(v or 0)), 2)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("max_participants", "registered_participants", mode="before")
    @classmethod
    def clean_int(cls, v):
        try:
            return max(0, int(v or 0))
        except (ValueError, TypeError):
            return 0

    @field_validator("available_spots", mode="before")
    @classmethod
    def clean_optional_int(cls, v):
        if v is None:
            return None
        try:
            return max(0, int(v))
        except (ValueError, TypeError):
            return None

    @field_validator("distance_km", "duration_hours", "rating", mode="before")
    @classmethod
    def clean_optional_float(cls, v):
        if v is None:
            return None
        try:
            return round(float(v), 2)
        except (ValueError, TypeError):
            return None

    @field_validator("travel_time_min", "reviews_count", mode="before")
    @classmethod
    def clean_optional_int_field(cls, v):
        if v is None:
            return None
        try:
            return max(0, int(v))
        except (ValueError, TypeError):
            return None

    @field_validator(
        "matched_criteria", "recurrence_days", "semantic_tags", mode="before"
    )
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v):
        if v is None:
            return "agency"
        normalized = str(v).strip().lower()
        return normalized if normalized in ("agency", "external") else "agency"

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, v):
        if v is None:
            return "internal"
        s = str(v).strip().lower()
        return s if s in ("internal", "mongodb") else "internal"

    @field_validator("activity_type", mode="before")
    @classmethod
    def normalize_activity_type(cls, v):
        valid = {"culture", "nature", "adventure", "relax", "city_experience", "unknown"}
        if not v or str(v).strip().lower() not in valid:
            return "unknown"
        return str(v).strip().lower()

    @field_validator("name", "hotel_name", "description", mode="before")
    @classmethod
    def clean_str(cls, v):
        if v is None:
            return None
        cleaned = str(v).strip()
        return cleaned if cleaned else None

    @field_validator("name", mode="before")
    @classmethod
    def require_name(cls, v):
        if not v or not str(v).strip():
            return "Activité sans nom"
        return str(v).strip()

    @field_validator("id", "activity_id", "booking_reference", mode="before")
    @classmethod
    def clean_id(cls, v):
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("destination", mode="before")
    @classmethod
    def clean_destination(cls, v):
        if v is None:
            return ""
        return str(v).strip()


class ActivityNodeOutput(BaseModel):
    activity_candidates: List[ActivityCandidate] = Field(default_factory=list)
    total_found:         int   = 0
    confidence:          float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 3)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("activity_candidates", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        return list(v)
