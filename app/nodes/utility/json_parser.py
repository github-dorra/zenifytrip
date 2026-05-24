import json
import re
from typing import Dict, Any


def parse_json_safely(text: str) -> Dict[str, Any]:
    """
    Extract and parse JSON from an LLM response.
    Handles: extra text before/after, markdown fences, truncated responses.
    """

    if not text or not isinstance(text, str):
        raise ValueError("Empty or non-string LLM response")

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences then retry
    stripped = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3. Find outermost {...} block
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 4. Truncated JSON recovery — close unclosed brackets
    start = stripped.find("{")
    if start != -1:
        fragment = stripped[start:]
        closing = _close_json(fragment)
        if closing:
            try:
                return json.loads(closing)
            except json.JSONDecodeError:
                pass

    raise ValueError(f"No JSON object found in LLM response: {text}")


def _close_json(fragment: str) -> str:
    """Auto-close a truncated JSON fragment — handles unclosed strings and brackets."""
    stack = []
    in_string = False
    escape = False

    for ch in fragment:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    if not stack and not in_string and fragment.strip().endswith(("}", "]")):
        return fragment

    tail = fragment.rstrip(", \n\r\t")
    if in_string:
        tail += '"'
    return tail + "".join(reversed(stack))