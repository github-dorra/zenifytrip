from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator
)

from typing import Optional, Literal, List


# =========================================================
# SUPPORTED INTENTS
# =========================================================

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


# =========================================================
# RESPONSE AGENT OUTPUT
# =========================================================

class ResponseAgentOutput(BaseModel):

    # Final natural response shown to user
    response_text: str = Field(
        default="",
        description="Natural language response generated for the user."
    )

    # Does the system still need user input?
    follow_up_needed: bool = Field(
        default=False,
        description="True if user clarification is still required."
    )

    # Optional clarification question
    clarification_question: Optional[str] = Field(
        default=None,
        description="Question to ask user when information is missing."
    )

    # Intent handled by response agent
    intent_handled: PrimaryIntent = Field(
        default="unsupported"
    )

    # Confidence score
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0
    )

    # Conversation mode
    response_mode: Literal[
        "greeting",
        "clarification",
        "guidance",
        "informative",
        "recommendation",
        "fallback"
    ] = "fallback"

    # Avoid infinite clarification loops
    should_stop_clarification: bool = False

    # Missing fields currently blocking
    blocking_fields: List[str] = []

    # Optional fields still missing
    optional_fields: List[str] = []

    # UX metadata
    tone: Literal[
        "friendly",
        "professional",
        "playful",
        "empathetic"
    ] = "friendly"

    # =====================================================
    # VALIDATORS
    # =====================================================

    @field_validator("tone", mode="before")
    @classmethod
    def normalize_tone(cls, v):
        allowed = {"friendly", "professional", "playful", "empathetic"}
        return v if v in allowed else "friendly"

    @field_validator("response_mode", mode="before")
    @classmethod
    def normalize_response_mode(cls, v):
        mapping = {"information": "informative", "info": "informative"}
        allowed = {"greeting", "clarification", "guidance", "informative", "recommendation", "fallback"}
        if v in mapping:
            return mapping[v]
        return v if v in allowed else "fallback"

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v):
        try:
            return max(0.0, min(float(v), 1.0))
        except Exception:
            return 0.0

    # =====================================================
    # CONSISTENCY RULES
    # =====================================================

    @model_validator(mode="after")
    def validate_logic(self):

        # No clarification question if follow up not needed
        if not self.follow_up_needed:
            self.clarification_question = None

        # clarification mode consistency
        if self.response_mode == "clarification":
            self.follow_up_needed = True

        # Avoid empty response
        if not self.response_text:
            self.response_text = (
                "Je suis là pour vous aider à organiser votre voyage 😊"
            )

        return self