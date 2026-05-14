from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Literal
import hashlib
import re




IntentDomain = Literal[
    "accommodation",
    "activity",
    "restaurant",
    "flight",
    "timing",
    "travel_info",
    "package",
]

SeasonType = Literal[
    "spring",
    "summer",
    "autumn",
    "winter",
]


# METADATA


class SemanticMetadata(BaseModel):
    constraints_detected: List[str] = Field(default_factory=list)
    seasonal_context: Optional[SeasonType] = None
    intent_domain: Optional[IntentDomain] = None
    primary_intent: Optional[str] = None

    @field_validator("constraints_detected", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


# ========================
# MAIN OUTPUT
# ========================

class SemanticOutput(BaseModel):
    semantic_query: Optional[str] = Field(default=None, max_length=50)

    global_keywords: List[str] = Field(default_factory=list)
    contextual_keywords: List[str] = Field(default_factory=list)

    metadata: SemanticMetadata = Field(default_factory=SemanticMetadata)

    # ---------------- VALIDATION ----------------

    @field_validator("global_keywords", "contextual_keywords", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("global_keywords", "contextual_keywords", mode="after")
    @classmethod
    def remove_duplicates(cls, values):
        seen = set()
        unique = []
        for v in values:
            if v not in seen:
                unique.append(v)
                seen.add(v)
        return unique

    @field_validator("global_keywords", "contextual_keywords", mode="after")
    @classmethod
    def limit_keywords(cls, values):
        return values[:8]

    @field_validator("global_keywords", "contextual_keywords", mode="after")
    @classmethod
    def normalize_keywords(cls, values):
        normalized = []
        for v in values:
            if isinstance(v, str):
                v = v.strip()
                if v:
                    normalized.append(v)
        return normalized



class SemanticStateUpdate(BaseModel):
    semantic_query: Optional[str] = Field(default=None, max_length=50)

    semantic_keywords: List[str] = Field(default_factory=list)
    semantic_tags: List[str] = Field(default_factory=list)

    semantic_metadata: SemanticMetadata = Field(default_factory=SemanticMetadata)

    semantic_cache_key: Optional[str] = None

    # ---------------- VALIDATION ----------------

    @field_validator("semantic_keywords", "semantic_tags", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("semantic_keywords", "semantic_tags", mode="after")
    @classmethod
    def remove_duplicates(cls, values):
        seen = set()
        unique = []
        for v in values:
            if v not in seen:
                unique.append(v)
                seen.add(v)
        return unique

    @field_validator("semantic_keywords", "semantic_tags", mode="after")
    @classmethod
    def validate_camel_case(cls, values):
        pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")
        for v in values:
            if not pattern.match(v):
                raise ValueError(f"Invalid keyword format: {v}")
        return values


# ========================
# CACHE KEY
# ========================

def generate_cache_key(data: Dict[str, Any]) -> str:
    raw = str(sorted(data.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]