"""
this node is used to merge profile data with intent fieds extractor to enrichie the context 
"""
from typing import Dict, Any
from app.nodes.core.Base_node import BaseNode, NodeConfig
from datetime import datetime, timedelta


class ContextMergerNode(BaseNode):

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="ContextMergerNode",
                node_type="technical",
            )
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        intent_result = state.get("intent_result", {})
        profile_data = state.get("profile_data", {})
        previous_merged = state.get("merged_context", {})

        # -----------------------------
        # SAFE extraction
        # -----------------------------
        primary_intent = intent_result.get("primary_intent")
        secondary_intents = intent_result.get("secondary_intents", [])
        action_type = intent_result.get("action_type")
        constraints = intent_result.get("constraints", {}) or {}

        merged = dict(previous_merged)  # IMPORTANT: copy safe

        profile_route = profile_data.get("route", {})
        profile_travel = profile_data.get("travel_preferences", {})
        profile_availability = profile_data.get("availability", {})
        traveller_profile = profile_data.get("traveller_profile", {})

        # -----------------------------
        # ROUTE
        # -----------------------------
        merged["origin"] = constraints.get("origin") or profile_route.get("origin")
        merged["destination"] = constraints.get("destination") or profile_route.get("destination")

        # -----------------------------
        # TRAVELERS
        # -----------------------------
        merged["travelers"] = constraints.get("travelers") or (
            1 + traveller_profile.get("child_count", 0) + traveller_profile.get("baby_count", 0)
        )

        # -----------------------------
        # BUDGET
        # -----------------------------
        if constraints.get("budget_level") is None:
            hotel_stars = profile_travel.get("hotel_stars", 0)
            merged["budget_level"] = (
                "luxury" if hotel_stars >= 5 else
                "premium" if hotel_stars >= 4 else
                "medium"
            )
        else:
            merged["budget_level"] = constraints.get("budget_level")

        # -----------------------------
        # INTERESTS (SAFE MERGE)
        # -----------------------------
        tags = traveller_profile.get("tags", [])
        traveller_tags = traveller_profile.get("traveller_tags", [])

        if isinstance(tags, str):
            tags = tags.split(",")
        if isinstance(traveller_tags, str):
            traveller_tags = traveller_tags.split(",")

        merged["interests"] = list(set(
            (constraints.get("interests") or [])
            + tags
            + traveller_tags
        ))

        # -----------------------------
        # ACCOMMODATION
        # -----------------------------
        existing_acc = constraints.get("accommodation_preferences", [])

        profile_acc = [
            profile_travel.get("meal_plan"),
            profile_travel.get("room_type"),
            profile_travel.get("hotel_name"),
        ]

        merged["accommodation_preferences"] = list(
            set([x for x in existing_acc + profile_acc if x])
        )

        # -----------------------------
        # FAMILY
        # -----------------------------
        merged["is_family"] = (
            traveller_profile.get("child_count", 0) > 0
            or traveller_profile.get("baby_count", 0) > 0
        )

        # -----------------------------
        # DATES
        # -----------------------------
        merged["start_date"] = constraints.get("start_date") or profile_availability.get("departure_date")
        merged["end_date"] = constraints.get("end_date") or profile_availability.get("return_date")
        merged["duration_days"] = constraints.get("duration_days") or profile_availability.get("duration_days")

        # -----------------------------
        # INTENT (ONLY ONCE HERE)
        # -----------------------------
        merged["primary_intent"] = primary_intent
        merged["secondary_intents"] = secondary_intents
        merged["action_type"] = action_type

        # -----------------------------
        # RETURN (ONLY ONE KEY)
        # -----------------------------
        state["merged_context"] = merged
        return state