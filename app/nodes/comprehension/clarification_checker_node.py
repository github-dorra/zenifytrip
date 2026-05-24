"""
    It analyzes the context extracted by the LLM and evaluates it
    against business requirements (Booking vs. Recommendation). 
    If critical data is missing, it halts the workflow, switches the suggestion mode to 'exploratory,' 
    and automatically generates a clarification question to guide the user
"""

from typing import Dict, Any, List
from app.nodes.core.Base_node import BaseNode,NodeConfig


class ClarificationCheckerNode(BaseNode):

    REQUIRED_FIELDS_BY_ACTION = {
        "booking": ["origin", "destination", "start_date", "travelers"],
        "recommendation": ["destination"],
        "information": []
    }
    NON_CRITICAL_FIELDS = ["travelers", "budget_level", "interests"]

    def __init__(self):
        super().__init__(
            NodeConfig(
                name= "ClarificationCheckerNode",
                node_type= "technical", )
            )
        
        
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        context = state.get("merged_context") or {}
        primary_intent = context.get("primary_intent")
        action_type = context.get("action_type")
        user_type = state.get("user_type", "native")

        # =========================
        # 1. SAFE MISSING DETECTION
        # =========================
        def is_missing(v):
            return v is None or v == "" or v == []

        missing_required = []
        missing_optional = []

        # only OPTIONAL detection here (safe)
        for k, v in context.items():
            if is_missing(v):
                missing_optional.append(k)

        # =========================
        # 2. REQUIRED LOGIC
        # =========================
        required_fields = self.REQUIRED_FIELDS_BY_ACTION.get(action_type, [])

        missing_required = [
            f for f in required_fields
            if is_missing(context.get(f))
        ]

        blocking_fields = missing_required.copy()

        # =========================
        # 3. CLEAN OPTIONALS (avoid override required)
        # =========================
        missing_optional = [
            f for f in set(missing_optional)
            if f not in blocking_fields
        ]

        for f in self.NON_CRITICAL_FIELDS:
            if is_missing(context.get(f)) and f not in missing_optional:
                missing_optional.append(f)

        # =========================
        # 4. DECISION ENGINE
        # =========================
        if len(blocking_fields) >= 2:
            mode = "exploratory"
            confidence = "low"

        elif len(blocking_fields) == 1:
            mode = "semi_exploratory"
            confidence = "medium"

        else:
            mode = "precise_plan"
            confidence = "high"

        # USER RÉEL ne descend jamais sous semi_exploratory
        if user_type == "real" and mode == "exploratory":
            mode = "semi_exploratory"
            confidence = "medium"

        next_action = "ask_clarification" if blocking_fields else "continue"

        # =========================
        # 5. UX GENERATION
        # =========================
        focus = self._select_focus(blocking_fields)

        clarification_question = None
        if blocking_fields:
            clarification_question = self._build_question(
                primary_intent,
                action_type,
                blocking_fields
            )

        # =========================
        # 6. RETURN
        # =========================
        return {

            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "blocking_fields": blocking_fields,

            "suggestion_mode": mode,
            "decision_confidence": confidence,

            "clarification_needed": bool(blocking_fields),
            "clarification_question": clarification_question,

            "next_action": next_action,
            "clarification_focus": focus,
        }

    # =========================
    # UX BUILDER (IMPORTANT)
    # =========================
    def _build_question(self, intent, action_type, fields):

        base = "Pouvez-vous préciser"

        if action_type == "booking":
            return f"{base} les éléments suivants : {', '.join(fields)} ?"

        if intent == "flight_recommendation":
            return f"{base} les informations de vol : {', '.join(fields)} ?"

        return f"{base} : {', '.join(fields)} ?"

    def _select_focus(self, blocking_fields: List[str]) -> List[str]:

        priority = ["destination", "origin", "start_date", "travelers"]

        selected = [f for f in priority if f in blocking_fields]

        return selected[:2] or blocking_fields[:2]