"""
feedback_logger_node.py — Phase 5

Mine les signaux implicites de satisfaction/rejet depuis conversation_history.
Produit feedback_event : {liked_types, rejected_types, session_id, traveller_id}
Aucun LLM — 100% déterministe.
"""
from typing import Any, Dict

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.utils.session_memory import extract_session_signals


class FeedbackLoggerNode(BaseNode):

    def __init__(self):
        super().__init__(NodeConfig(name="feedback_logger", node_type="technical"))

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        signals = extract_session_signals(state.get("conversation_history") or [])

        # traveller_id disponible dans plusieurs champs selon le chemin parcouru
        traveller_id = (
            state.get("travellerId")
            or (state.get("profile_data") or {}).get("id")
            or (state.get("profile_data") or {}).get("traveller_id")
        )

        feedback_event = {
            "liked_types":    signals.get("liked_types", []),
            "rejected_types": signals.get("rejected_types", []),
            "session_id":     state.get("session_id"),
            "traveller_id":   traveller_id,
        }

        if feedback_event["rejected_types"] or feedback_event["liked_types"]:
            self.logger.info(
                f"[FeedbackLogger] traveller={traveller_id} "
                f"rejected={feedback_event['rejected_types']} "
                f"liked={feedback_event['liked_types']}"
            )

        return {"feedback_event": feedback_event}
