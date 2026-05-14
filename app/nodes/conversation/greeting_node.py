from typing import Dict, Any
from app.nodes.core.Base_node import BaseNode,NodeConfig
from app.nodes.core.session_bootstrap import bootstrap_session


class GreetingNode(BaseNode):
    def __init__(self):
        config = NodeConfig(name="greeting")
        super().__init__(config)

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        
        # injecte traveller_id + session context
        state = bootstrap_session(state)
        user_message = state.get("user_message", "")

        return {
            **state,

            "normalized_message": user_message.strip().lower(),
        }


