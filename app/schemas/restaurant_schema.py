from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional


class RestaurantCandidate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    price_level: Optional[int] = None
    cuisine_types: List[str] = Field(default_factory=list)
    is_open_now: Optional[bool] = None
    distance_km: Optional[float] = None
    photo_reference: Optional[str] = None
    match_score: float = 0.0
    user_score: float = 0.0   # posé par MongoRestaurantService ; copié vers match_score par sync_user_score_to_match_score
    matched_criteria: List[str] = Field(default_factory=list)
    establishment_types: List[str] = Field(default_factory=list)
    tier: str = "text_search"
    source: str = "google_places"
    # Posé par la source (Mongo 0.6 / Google 0.20) — lu en priorité 1 par ranking_node
    business_score: Optional[float] = None
    recommendation_reason: Optional[str] = None
    place_details: Optional[str] = None  # texte enrichi Place Details → passé au ranking_node LLM

    @model_validator(mode="before")
    @classmethod
    def sync_user_score_to_match_score(cls, values):
        """
        MongoRestaurantService pose user_score mais pas match_score.
        Google Places / SerpAPI posent match_score mais pas user_score.
        Si match_score absent/nul et user_score présent → copie vers match_score
        pour que data_merger le voie via c.get("match_score").
        """
        if isinstance(values, dict):
            ms = float(values.get("match_score") or 0.0)
            us = float(values.get("user_score")  or 0.0)
            if ms == 0.0 and us > 0.0:
                values["match_score"] = us
        return values

    @field_validator("rating", mode="before")
    @classmethod
    def clamp_rating(cls, v):
        if v is None:
            return None
        try:
            return round(max(1.0, min(float(v), 5.0)), 1)
        except (ValueError, TypeError):
            return None

    @field_validator("match_score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 4)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("price_level", mode="before")
    @classmethod
    def clamp_price(cls, v):
        if v is None:
            return None
        try:
            return max(0, min(int(v), 4))
        except (ValueError, TypeError):
            return None

    @field_validator("distance_km", mode="before")
    @classmethod
    def round_distance(cls, v):
        if v is None:
            return None
        try:
            return round(float(v), 2)
        except (ValueError, TypeError):
            return None

    @field_validator("cuisine_types", "matched_criteria", "establishment_types", mode="before")
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
            return "text_search"
        return str(v).strip().lower()


class RestaurantNodeOutput(BaseModel):
    restaurant_candidates: List[RestaurantCandidate] = Field(default_factory=list)
    total_found: int = 0
    search_mode: str = "none"
    confidence: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 3)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("restaurant_candidates", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        return list(v)
