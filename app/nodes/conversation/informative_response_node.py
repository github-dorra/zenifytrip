"""
InformativeResponseNode — Agent 3
Réponse experte pour travel_question et booking_question.

Chemin : information_node → informative_response_node → END

Gère :
  - dynamic_factual : présente les données Tavily (ou répond de mémoire avec caveat)
  - booking_info    : détails de réservation
  - follow_up_place : localisation d'un candidat précédent
  - weather         : météo avec conseils pratiques
  - session_planning: résumé planifié
  - factual         : connaissance stable Tunisie
"""
import datetime
import json
from typing import Any, Dict

from app.nodes.core.Base_node import BaseNode
from app.config.definitions import INFORMATIVE_RESPONSE_CONFIG
from app.prompts.informative_response_prompt import INFORMATIVE_RESPONSE_PROMPT
from app.schemas.reponse_schema import ResponseAgentOutput
from app.nodes.utility.json_parser import parse_json_safely


class InformativeResponseNode(BaseNode):

    def __init__(self):
        super().__init__(INFORMATIVE_RESPONSE_CONFIG)

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_message = (
            state.get("normalized_message") or state.get("user_message") or ""
        )
        merged_context    = state.get("merged_context") or {}
        intent_result     = state.get("intent_result")  or {}
        information_context = state.get("information_context")

        primary_intent = intent_result.get("primary_intent", "travel_question")
        language       = intent_result.get("language", "fr")
        destination    = merged_context.get("destination") or "Tunisie"

        information_context_str = (
            json.dumps(information_context, ensure_ascii=False)
            if information_context else "null"
        )

        prompt = INFORMATIVE_RESPONSE_PROMPT.format(
            user_message=user_message,
            language=language,
            destination=destination,
            information_context=information_context_str,
            year=datetime.datetime.now().year,
        )

        raw_output = ""
        try:
            response   = self.call_llm(prompt=prompt)
            raw_output = response.get("content", "")
            parsed     = parse_json_safely(raw_output)
            if not isinstance(parsed, dict):
                raise ValueError("LLM output is not valid JSON")
            output = ResponseAgentOutput(**parsed)

        except Exception as e:
            self.logger.error(
                f"[InformativeResponseNode] error={type(e).__name__} | {e} | raw={raw_output}"
            )
            output = ResponseAgentOutput(
                response_text=(
                    "Je vais vous aider avec cette question. "
                    "Pourriez-vous la reformuler ?"
                ),
                follow_up_needed=True,
                intent_handled=primary_intent,
                confidence=0.2,
            )

        return {
            "response_agent_result": output.model_dump(),
            "final_answer":          output.response_text,
            "follow_up_needed":      output.follow_up_needed,
            "clarification_question": output.clarification_question,
            "intent_handled":        output.intent_handled,
            "response_confidence":   output.confidence,
        }
