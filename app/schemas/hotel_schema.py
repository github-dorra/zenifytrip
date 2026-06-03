from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class CoordinatesInfo(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None

    @field_validator("lat", "lng", mode="before")
    @classmethod
    def clean_float(cls, v):
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None


class HotelCandidate(BaseModel):
    id: str
    name: Optional[str] = None

    # Standing
    stars: int = 0

    # Localisation
    zone_name: Optional[str] = None
    address: Optional[str] = None
    coordinates: Optional[CoordinatesInfo] = None

    # Descriptions — passées brutes au LLM downstream (final_response_node)
    short_description: Optional[str] = None
    long_description: Optional[str] = None

    # Offres agence — source : /api/hotel-services
    services: List[str] = Field(default_factory=list)

    # Priorité commerciale
    is_partner: bool = False
    tier: Optional[str] = None          # "partner" | "catalogue"

    # Scores
    score: float = 0.0                  # score final (0.7×user + 0.3×business)
    business_score: float = 0.0
    user_score: float = 0.0

    # Critères satisfaits — pour que ranking_node sache ce qui a matché
    matched_criteria: List[str] = Field(default_factory=list)

    # =========================================================
    # VALIDATORS — normalise au lieu de planter le pipeline
    # =========================================================

    @field_validator("score", "business_score", "user_score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        return max(0.0, min(float(v or 0), 1.0))

    @field_validator("stars", mode="before")
    @classmethod
    def clean_stars(cls, v):
        try:
            return max(0, int(v or 0))
        except (ValueError, TypeError):
            return 0

    @field_validator("services", "matched_criteria", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v):
        if v is None:
            return None
        normalized = str(v).strip().lower()
        return normalized if normalized in ("partner", "catalogue") else None

    @field_validator("name", "zone_name", "address", mode="before")
    @classmethod
    def clean_str(cls, v):
        if v is None:
            return None
        return str(v).strip() or None


class HotelNodeOutput(BaseModel):
    hotel_candidates: List[HotelCandidate] = Field(default_factory=list)
    total_found: int = 0
    filters_applied: List[str] = Field(default_factory=list)
    confidence: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v):
        return max(0.0, min(float(v or 0), 1.0))

    @field_validator("hotel_candidates", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        return v

    @field_validator("filters_applied", mode="before")
    @classmethod
    def ensure_filters_list(cls, v):
        if v is None:
            return []
        return v
