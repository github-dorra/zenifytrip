import re
from typing import Dict, Any, List

from app.nodes.core.Base_node import BaseNode
from app.nodes.definitions import RESTAURANT_C_CONFIG
from app.prompts.recommendation.restaurant_c_prompt import RESTAURANT_C_PROMPT
from app.nodes.utility.json_parser import parse_json_safely
from app.schemas.restaurant_schema import RestaurantCandidate
from app.services.restaurant_service_c import RestaurantServiceC


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())
    return text[:30]


class RestaurantNodeC(BaseNode):
    """
    Approche C — Tavily Google Search + LLM Groq.
    Tavily fournit les données réelles, le LLM structure et enrichit.
    """

    def __init__(self):
        super().__init__(RESTAURANT_C_CONFIG)
        self._last_tokens: Dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}
        self._last_benchmark: Dict       = {}

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # ── 1. EXTRACTION — même mapping que A et B ──────────────────
        semantic_query  = state.get("semantic_query") or ""
        global_keywords = state.get("global_keywords") or []

        merged_context  = state.get("merged_context") or {}
        destination     = merged_context.get("destination") or "Tunisie"
        budget_level    = merged_context.get("budget_level") or "medium"
        is_family       = merged_context.get("is_family", False)

        suggestion_mode = state.get("suggestion_mode") or "exploratory"
        max_results     = 15 if suggestion_mode == "exploratory" else 10

        # ── 2. TAVILY SEARCH — données réelles depuis Google ─────────
        try:
            formatted_results, benchmark = RestaurantServiceC.get_search_context(
                semantic_query=semantic_query,
                destination=destination,
                max_results=5,
            )
            self._last_benchmark = benchmark
        except Exception as e:
            self.logger.error(f"RestaurantNodeC Tavily error: {e}")
            formatted_results = "Aucun résultat disponible."
            self._last_benchmark = {"tavily_calls": 0, "cache_hit": False, "latency_ms": 0}

        # ── 3. PROMPT — LLM reçoit les vraies données ─────────────────
        prompt = RESTAURANT_C_PROMPT.format(
            destination     = destination,
            semantic_query  = semantic_query,
            global_keywords = ", ".join(global_keywords) if global_keywords else "aucun",
            search_results  = formatted_results,
            max_results     = max_results,
        )

        # ── 4. APPEL LLM ─────────────────────────────────────────────
        tokens_used = {"prompt": 0, "completion": 0, "total": 0}
        raw_list    = []

        try:
            response = self.call_llm(prompt=prompt)
            content  = response.get("content", "")

            usage = response.get("usage") or {}
            tokens_used["prompt"]     = usage.get("prompt_tokens", 0)
            tokens_used["completion"] = usage.get("completion_tokens", 0)
            tokens_used["total"]      = usage.get("total_tokens", 0)
            self._last_tokens         = tokens_used

            data = parse_json_safely(content)
            if isinstance(data, dict):
                raw_list = data.get("restaurants", [])
            elif isinstance(data, list):
                raw_list = data

        except Exception as e:
            self.logger.error(f"RestaurantNodeC LLM error: {e}")
            raw_list = []

        # ── 5. ENRICHISSEMENT — id + tier + source ───────────────────
        enriched = []
        for i, item in enumerate(raw_list):
            if not isinstance(item, dict):
                continue
            name = item.get("name") or f"restaurant_{i}"
            item["id"]     = f"tavily_{i}_{_slugify(name)}"
            item["tier"]   = "tavily_llm"
            item["source"] = "tavily_google_search"
            enriched.append(item)

        # ── 6. VALIDATION PYDANTIC ───────────────────────────────────
        validated: List[Dict] = []
        pydantic_failures = 0

        for raw in enriched:
            try:
                candidate = RestaurantCandidate(**raw)
                validated.append(candidate.model_dump())
            except Exception as e:
                pydantic_failures += 1
                self.logger.warning(f"RestaurantCandidate skip: {e}")

        # ── 7. CONFIANCE ─────────────────────────────────────────────
        confidence = self.calculate_confidence(
            model_confidence=0.8,       # LLM travaille sur données réelles → confiance +
            required_fields_score=1.0 if destination else 0.5,
            schema_validation_score=1.0 if pydantic_failures == 0 else 0.6,
            source_reliability_score=0.9 if validated else 0.0,
        )

        # ── 8. LOGS ──────────────────────────────────────────────────
        self.logger.info(
            f"candidates={len(validated)} | "
            f"tavily_calls={self._last_benchmark.get('tavily_calls', 0)} | "
            f"tavily_cache={'HIT' if self._last_benchmark.get('cache_hit') else 'MISS'} | "
            f"tavily_latency={self._last_benchmark.get('latency_ms', 0)}ms | "
            f"tokens=prompt:{tokens_used['prompt']} "
            f"completion:{tokens_used['completion']} total:{tokens_used['total']} | "
            f"pydantic_fail={pydantic_failures} | "
            f"confidence={confidence:.3f}"
        )

        # ── 9. TRI + RETOUR ──────────────────────────────────────────
        validated.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return {
            "restaurant_candidates": validated,
        }
