from typing import Dict, Any 
from app.nodes.core.Base_node import BaseNode 
from app.prompts.final_response_prompt import RESPONSE_AGENT_PROMPT
from app.config.definitions import RESPONSE_CONFIG
from app.graph.state import GraphState 
from app.schemas.reponse_schema import (ResponseAgentOutput,PrimaryIntent)
from app.nodes.utility.json_parser import parse_json_safely




class FinalResponseNode(BaseNode): 
    def __init__(self): 
        super().__init__( 
            RESPONSE_CONFIG) 
        
        
    
    def run(self,state: Dict[str, Any]) -> Dict[str, Any]:

        # =====================================================
        # SAFE STATE EXTRACTION
        # =====================================================

        user_message = (
            state.get("normalized_message")
            or state.get("user_message")
            or ""
        )

        merged_context = (
            state.get("merged_context")
            or {}
        )

        constraints = (
            state.get("intent_result", {}).get("constraints")
            or {}
        )

        primary_intent = (
            merged_context.get("primary_intent")
            or state.get("primary_intent")
            or "unsupported"
        )

        secondary_intents = (
            merged_context.get("secondary_intents")
            or state.get("secondary_intents")
            or []
        )

        action_type = (
            merged_context.get("action_type")
            or state.get("action_type")
            or "none"
        )

        clarification_needed = state.get(
            "clarification_needed",
            False
        )

        clarification_question = state.get(
            "clarification_question"
        )

        missing_required = state.get(
            "missing_required",
            []
        )

        suggestion_mode = state.get(
            "suggestion_mode"
        )

        previous_user_context = (
            state.get("profile_data")
            or {}
        )

        # =====================================================
        # PROMPT
        # =====================================================

        prompt = RESPONSE_AGENT_PROMPT.format(
            user_message=user_message,
            primary_intent=primary_intent,
            secondary_intents=secondary_intents,
            action_type=action_type,
            constraints=constraints,
            merged_context=merged_context,
            clarification_needed=clarification_needed,
            clarification_question=clarification_question,
            missing_required=missing_required,
            suggestion_mode=suggestion_mode,
            previous_user_context=previous_user_context,
            available_intents=", ".join(
                PrimaryIntent.__args__
            ),
        )

        raw_output = ""

        # =====================================================
        # LLM EXECUTION
        # =====================================================

        try:

            response = self.call_llm(
                prompt=prompt
            )

            raw_output = response.get(
                "content",
                ""
            )

            parsed = parse_json_safely(
                raw_output
            )

            if not isinstance(parsed, dict):

                raise ValueError(
                    "LLM output is not valid JSON"
                )

            output = ResponseAgentOutput(
                **parsed
            )

        # =====================================================
        # FALLBACK
        # =====================================================

        except Exception as e:

            self.logger.error(
                f"[ResponseAgentNode] "
                f"Invalid output | "
                f"error={type(e).__name__} | "
                f"details={e} | "
                f"raw={raw_output}"
            )

            fallback_text = (
                clarification_question
                if clarification_needed
                else (
                    "Je peux vous aider à organiser votre voyage ✈️"
                )
            )

            output = ResponseAgentOutput(
                response_text=fallback_text,
                follow_up_needed=clarification_needed,
                clarification_question=clarification_question,
                intent_handled=primary_intent,
                confidence=0.2,
            )

        # =====================================================
        # RETURN UPDATED STATE
        # =====================================================

        return {

            "response_agent_result":
                output.model_dump(),

            "final_answer":
                output.response_text,

            "follow_up_needed":
                output.follow_up_needed,

            "clarification_question":
                output.clarification_question,

            "intent_handled":
                output.intent_handled,

            "response_confidence":
                output.confidence,
        }