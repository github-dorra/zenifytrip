from typing import Dict, Any
from app.nodes.core.Base_node import BaseNode,NodeConfig


class GreetingNode(BaseNode):
    def __init__(self):
        config = NodeConfig(name="greeting")
        super().__init__(config)

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        
        user_message = state.get("user_message", "")

        return {
            "normalized_message": user_message.strip().lower(),
        }


