import hashlib
import json
import logging
import time
from typing import Dict, Any, List, Tuple, Optional

from app.config.settings import TAVILY_API_KEY
from app.services.cache_service import cache, SimpleTTLCache

logger = logging.getLogger(__name__)

TTL = SimpleTTLCache.TTL_RESTAURANTS  # 259200s = 72h


class RestaurantServiceC:
    """
    Approche C — Tavily Google Search + LangChain tool.
    Retourne des résultats web réels pour ancrer le LLM.
    """

    @staticmethod
    def _cache_key(query: str) -> str:
        h = hashlib.md5(query.encode()).hexdigest()[:10]
        return f"tavily_rest_{h}"

    # ------------------------------------------------------------------
    # Recherche Tavily via LangChain TavilySearchResults
    # ------------------------------------------------------------------

    @staticmethod
    def search(query: str, max_results: int = 5) -> Tuple[List[Dict], int, bool]:
        """
        Retourne (results, api_calls, cache_hit).
        results = liste de {title, content, url}
        """
        cache_key = RestaurantServiceC._cache_key(query)
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info(f"RestaurantServiceC: cache HIT [{cache_key}]")
            return cached, 0, True

        try:
            from langchain_community.tools.tavily_search import TavilySearchResults
            import os
            os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY or ""

            tool = TavilySearchResults(max_results=max_results)
            raw  = tool.invoke({"query": query})

            # TavilySearchResults retourne une liste de dicts ou une string
            if isinstance(raw, str):
                results = [{"title": "", "content": raw, "url": ""}]
            elif isinstance(raw, list):
                results = [
                    {
                        "title":   r.get("title", ""),
                        "content": r.get("content", ""),
                        "url":     r.get("url", ""),
                    }
                    for r in raw
                ]
            else:
                results = []

            cache.set(cache_key, results, TTL)
            return results, 1, False

        except Exception as e:
            logger.error(f"RestaurantServiceC.search error: {e}")
            return [], 1, False

    # ------------------------------------------------------------------
    # Formater les résultats pour le prompt LLM
    # ------------------------------------------------------------------

    @staticmethod
    def format_results_for_prompt(results: List[Dict]) -> str:
        if not results:
            return "Aucun résultat trouvé."
        lines = []
        for i, r in enumerate(results, 1):
            title   = r.get("title", "").strip()
            content = r.get("content", "").strip()[:400]  # tronquer pour le prompt
            url     = r.get("url", "").strip()
            lines.append(f"[{i}] {title}\n    {content}\n    Source: {url}")
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    @staticmethod
    def get_search_context(
        semantic_query: str,
        destination:    Optional[str],
        max_results:    int = 5,
    ) -> Tuple[str, Dict]:
        """
        Lance la recherche Tavily et retourne (formatted_results, benchmark).
        """
        query = semantic_query or f"restaurants {destination or 'tunisie'}"

        benchmark = {
            "tavily_calls": 0,
            "cache_hit":    False,
            "latency_ms":   0,
        }

        t0 = time.time()
        results, calls, hit = RestaurantServiceC.search(query, max_results)
        benchmark["latency_ms"]   = int((time.time() - t0) * 1000)
        benchmark["tavily_calls"] = calls
        benchmark["cache_hit"]    = hit

        formatted = RestaurantServiceC.format_results_for_prompt(results)
        return formatted, benchmark
