from typing import Dict, Any, Literal, Optional,List

from app.schemas.intent_schema import TravelConstraints, IntentClassifierOutput, PrimaryIntent, SecondaryIntent, ActionType, LanguageCode
from app.nodes.core.Base_node import BaseNode
from app.config.definitions import INTENT_CLASSIFIER_CONFIG
from app.prompts.intent_classifier_prompt import INTENT_CLASSIFIER_PROMPT
from app.nodes.utility.json_parser import parse_json_safely




class IntentClassifierNode(BaseNode):

    def __init__(self):
        super().__init__(
            INTENT_CLASSIFIER_CONFIG
        )
        

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:           # state -> new state enrechied
        user_message=state.get("normalized_message", "")
        conversation_history = state.get("conversation_history", [])
        recent_history = conversation_history[-5:]
        
        # nettoyer le formet de sortie de history conversation
        formatted_history = "\n".join(
        [
                f"{msg['role']}: {msg['content']}"
                for msg in recent_history
            ]
        )
        
        previous_context = {
            "last_intent": state.get("intent_result", {}).get("primary_intent"),
            "memory": formatted_history,
            "merged_context": state.get("merged_context",{})
        }
        
        prompt = INTENT_CLASSIFIER_PROMPT.format(
            user_message=user_message,

            conversation_history=previous_context["memory"],

            merged_context=previous_context["merged_context"],

            last_intent=previous_context["last_intent"],
        )
        
        
        
        raw=""
        try:
            response = self.call_llm(prompt=prompt)
            raw = response.get("content", "")

            data = parse_json_safely(raw)

            if not isinstance(data, dict):
                raise ValueError("Invalid JSON structure")

        except Exception as e:
            self.logger.error(
        f"Invalid LLM output. raw={raw!r}, error={type(e).__name__}: {e}"
    )

            return {
                "intent_result": {
                    "primary_intent": "unsupported",
                    "secondary_intents": [],
                    "action_type": "recommendation",
                    "constraints": TravelConstraints().model_dump(),
                    "language": "fr",
                    "confidence": 0.0,
    }}

        # -------------------------
        # SAFE NORMALIZATION LAYER
        # -------------------------

        # primary_intent
        primary_intent = data.get("primary_intent")
        if primary_intent not in PrimaryIntent.__args__:
            primary_intent = "unsupported"
            
         # secondary_intents
        secondary_intents = data.get("secondary_intents", [])
        if not isinstance(secondary_intents, list):
            secondary_intents = []
        # remove duplicates of primary
        secondary_intents = [s for s in secondary_intents if s != primary_intent]

        # action_type
        action_type = data.get("action_type")
        if action_type not in ActionType.__args__ or action_type is None:
            action_type = "recommendation"
            
        
        # constraints
        constraints_data = data.get("constraints", {})
        if not isinstance(constraints_data, dict):
            constraints_data = {}

        try:
            constraints = TravelConstraints(**constraints_data)
        except Exception as e:
            self.logger.warning(f"Failed to parse constraints: {e}")
            constraints = TravelConstraints()

        # language
        language = data.get("language", "fr")
        if language not in LanguageCode.__args__:
            language = "fr"
            
        # confidence
        confidence = data.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(float(confidence), 1.0))
        except Exception:
            confidence = 0.0

        # -------------------------
        # RETURN UPDATED STATE
        # -------------------------
        return {
            "intent_result":{
            "primary_intent": primary_intent,
            "secondary_intents": secondary_intents,
            "action_type": action_type,
            "constraints": constraints.model_dump(),
            "language": language,
            "confidence": confidence,
        }}