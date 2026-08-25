from typing import Any, Dict, List
from pydantic import BaseModel, Field, field_validator

VALID_SERVICES = {"hotel_node", "flight_node", "activity_node", "restaurant_node"}


class OrchestratorOutput(BaseModel):
    requested_services:      List[str]              = Field(default_factory=list)
    reasoning:               str                    = ""
    constraints_per_service: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    confidence:              float                  = 0.8
    excluded_services:       Dict[str, str]         = Field(default_factory=dict)

    @field_validator("requested_services")
    @classmethod
    def only_valid_services(cls, v):
        return [s for s in (v or []) if s in VALID_SERVICES]

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v):
        return max(0.0, min(float(v or 0.8), 1.0))
