"""
this node is used to merge profile data with intent fieds extractor to enrichie the context 
"""
import re
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
        # ROUTE — preserve si rien de nouveau
        # -----------------------------
        new_origin = constraints.get("origin") or profile_route.get("origin")
        new_destination = constraints.get("destination") or profile_route.get("destination")
        if new_origin:      merged["origin"]      = new_origin
        if new_destination: merged["destination"] = new_destination

        # -----------------------------
        # TRAVELERS — preserve si valeur explicite > 1 déjà connue
        # -----------------------------
        new_travelers = constraints.get("travelers", 1)
        prev_travelers = merged.get("travelers", 1)
        if new_travelers > 1:
            merged["travelers"] = new_travelers
        elif prev_travelers > 1:
            merged["travelers"] = prev_travelers
        else:
            merged["travelers"] = 1 + (traveller_profile.get("child_count") or 0) + (traveller_profile.get("baby_count") or 0) or 1

        # -----------------------------
        # BUDGET — preserve si rien de nouveau
        # -----------------------------
        new_budget = constraints.get("budget_level")
        if new_budget:
            merged["budget_level"] = new_budget
        elif "budget_level" not in merged:
            raw_stars = profile_travel.get("hotel_stars")
            match = re.search(r'\d+', str(raw_stars)) if raw_stars is not None else None
            hotel_stars = int(match.group()) if match else 0
            merged["budget_level"] = (
                "luxury" if hotel_stars >= 5 else
                "premium" if hotel_stars >= 4 else
                "medium"
            )

        # -----------------------------
        # INTERESTS — accumulation multi-tour
        # -----------------------------
        tags_data = profile_data.get("tags", {}) or {}
        tags = tags_data.get("tags") or []
        traveller_tags = tags_data.get("travellerTags") or []

        if isinstance(tags, str):
            tags = tags.split(",")
        if isinstance(traveller_tags, str):
            traveller_tags = traveller_tags.split(",")

        merged["interests"] = list(set(
            (merged.get("interests") or [])
            + (constraints.get("interests") or [])
            + tags
            + traveller_tags
        ))

        # -----------------------------
        # PREFERENCES — accumulation multi-tour
        # -----------------------------
        for pref_key in ["activity_preferences", "restaurant_preferences", "flight_preferences"]:
            new_prefs = constraints.get(pref_key) or []
            existing_prefs = merged.get(pref_key) or []
            merged[pref_key] = list(set(existing_prefs + new_prefs))

        # ACCOMMODATION — accumulation + profil
        profile_acc = [
            profile_travel.get("meal_plan"),
            profile_travel.get("room_type"),
            profile_travel.get("hotel_name"),
        ]
        new_acc = constraints.get("accommodation_preferences") or []
        existing_acc = merged.get("accommodation_preferences") or []
        merged["accommodation_preferences"] = list(
            set([x for x in existing_acc + new_acc + profile_acc if x])
        )

        # -----------------------------
        # FAMILY
        # -----------------------------
        merged["is_family"] = (
            (traveller_profile.get("child_count") or 0) > 0
            or (traveller_profile.get("baby_count") or 0) > 0
            or merged.get("travelers", 1) > 2
        )

        # -----------------------------
        # DATES — preserve si rien de nouveau
        # -----------------------------
        new_start    = constraints.get("start_date")    or profile_availability.get("departure_date")
        new_end      = constraints.get("end_date")      or profile_availability.get("return_date")
        new_duration = constraints.get("duration_days") or profile_availability.get("duration_days")
        new_nat_date = constraints.get("natural_date_text")

        if new_start:    merged["start_date"]        = new_start
        if new_end:      merged["end_date"]           = new_end
        if new_duration: merged["duration_days"]      = new_duration
        if new_nat_date: merged["natural_date_text"]  = new_nat_date

        # -----------------------------
        # INTENT (ONLY ONCE HERE)
        # -----------------------------
        merged["primary_intent"] = primary_intent
        merged["secondary_intents"] = secondary_intents
        merged["action_type"] = action_type

        # -----------------------------
        # RETURN (ONLY ONE KEY)
        # -----------------------------
        return {"merged_context": merged}