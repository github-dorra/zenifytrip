# define the standard schema of the intent classifier output
# it's a data contract bettween llm and the rest of system 


from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any, Literal


PrimaryIntent = Literal[
    "greeting",
    "flight_recommendation",
    "accommodation_recommendation",
    "restaurant_recommendation",
    "activity_recommendation",
    "day_planning",
    "trip_package_recommendation",
    "travel_question",
    "profile_update",
    "booking_question",
    "feedback",
    "unsupported",
]


SecondaryIntent = Literal[
    "flight_recommendation",
    "accommodation_recommendation",
    "restaurant_recommendation",
    "activity_recommendation",
]


ActionType = Literal[
    "recommendation",
    "booking",
    "information",
    "profile_update",
    "none",
]


BudgetLevel = Literal["low", "medium", "luxury"]
LanguageCode = Literal["en", "fr", "es", "de", "ar"]


class TravelConstraints(BaseModel):
    """
    Raw constraints extracted by the Intent Agent.

    Important:
    - Do not apply business validation here.
    - Do not calculate missing fields here.
    - Do not generate clarification here.
    """

    origin: Optional[str] = None
    destination: Optional[str] = None

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_days: Optional[int] = None
    natural_date_text: Optional[str] = None

    travelers: Optional[int] = 1
    budget_level: Optional[BudgetLevel] = None

    interests: List[str] = Field(default_factory=list)
    special_requirements: List[str] = Field(default_factory=list)
    activity_preferences: List[str] = Field(default_factory=list)
    restaurant_preferences: List[str] = Field(default_factory=list)
    accommodation_preferences: List[str] = Field(default_factory=list)
    flight_preferences: List[str] = Field(default_factory=list)

    @field_validator("interests", "special_requirements", mode="before")
    @classmethod
    def ensure_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("duration_days", "travelers")
    @classmethod
    def positive_int_or_none(cls, value):
        if value is None:
            return value
        if value <= 0:
            return None
        return value
    
    
class IntentClassifierOutput(BaseModel):
    primary_intent: PrimaryIntent
    secondary_intents: List[SecondaryIntent] = Field(default_factory=list)

    action_type: ActionType

    constraints: TravelConstraints = Field(default_factory=TravelConstraints)

    language: LanguageCode = "fr"

    confidence: float = 0.0
    
    # ---------------- validation ----------------
    @field_validator("secondary_intents", mode="before")
    @classmethod
    def ensure_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value):
        return max(0.0, min(float(value or 0), 1.0))

    @model_validator(mode="after")
    def remove_primary_from_secondary(self):
        self.secondary_intents = [
            s for s in self.secondary_intents
            if s != self.primary_intent
        ]
        return self