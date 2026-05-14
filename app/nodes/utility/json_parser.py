import json
import re
from typing import Dict, Any


def parse_json_safely(text: str) -> Dict[str, Any]:
    """
    Extract and parse JSON from an LLM response.
    Works even if the model adds text before or after JSON.
    """

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text}")

    return json.loads(match.group(0))