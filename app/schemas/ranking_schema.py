from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Optional


class RankedCandidate(BaseModel):
    rank:           int
    domain:         str
    ranked_score:   float
    user_score:     float
    business_score: float
    name:           Optional[str] = None
    recommendation_reason: Optional[str] = None
    extra:          Dict[str, Any] = Field(default_factory=dict)

    @field_validator("ranked_score", "user_score", "business_score", mode="before")
    @classmethod
    def clamp(cls, v):
        try:
            return round(max(0.0, min(float(v or 0), 1.0)), 4)
        except (ValueError, TypeError):
            return 0.0


class RankingOutput(BaseModel):
    ranked_results: List[Dict[str, Any]] = Field(default_factory=list)
    total_ranked:   int = 0
