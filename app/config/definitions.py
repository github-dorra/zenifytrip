"""
AI Agent definitions — only the agents that still require LLM reasoning.
The other data-fetching agents (flights, accommodation, activities, logistics)
are now pure API services and no longer need AI.
"""
from app.nodes.core.Base_node import NodeConfig


INTENT_CLASSIFIER_CONFIG = NodeConfig(
    name="intent_classifier",
    node_type="comprehension",
    provider="groq",
    model="llama-3.3-70b-versatile",
    temperature=0.0,
    max_tokens=800,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=3600,
)

SEMANTIC_CONFIG = NodeConfig(
    name="semantic_agent",
    node_type="comprehension",
    provider="groq",
    model="llama-3.3-70b-versatile",  # llama-4-scout retire du catalogue Groq (404 model_not_found, verifie 2026-07-28)
    temperature=0.0,   # JSON déterministe — pas de créativité nécessaire
    max_tokens=800,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=3600,
)

RANKING_CONFIG = NodeConfig(
    name="ranking",
    node_type="llm_agent",
    provider="groq",
    model="llama-3.1-8b-instant",   # ranking = Python pur, config de secours uniquement
    temperature=0.2,
    max_tokens=800,
    response_format="json",
    cache_enabled=False,
)

DAY_PLANNER_CONFIG = NodeConfig(
    name="day_planner",
    node_type="llm_agent",
    provider="groq",
    model="llama-3.3-70b-versatile",  # llama-4-scout retire du catalogue Groq (404 model_not_found, verifie 2026-07-28)
    temperature=0.3,
    max_tokens=3000,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=1800,
)



# Agent clarification (chemin ask_clarification → final_response_node existant)
RESPONSE_CONFIG = NodeConfig(
    name="response",
    node_type="llm_agent",
    provider="groq",
    model="llama-3.3-70b-versatile",  # qualité française optimale — prouvé sur intent_classifier
    temperature=0.4,
    max_tokens=2500,
    response_format="json",
    cache_enabled=False,
)

# Agent présentation des recommandations (chemin data_merger → recommendation_response_node)
RECOMMENDATION_RESPONSE_CONFIG = NodeConfig(
    name="recommendation_response",
    node_type="llm_agent",
    provider="groq",
    model="llama-3.3-70b-versatile",  # llama-4-scout retire du catalogue Groq (404 model_not_found, verifie 2026-07-28)
    temperature=0.4,
    max_tokens=3000,
    response_format="json",
    cache_enabled=False,
)


RESTAURANT_B_CONFIG = NodeConfig(
    name="restaurant_node_b",
    node_type="llm_agent",
    provider="groq",
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    max_tokens=2500,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=259200,  # 72h
)

RESTAURANT_C_CONFIG = NodeConfig(
    name="restaurant_node_c",
    node_type="llm_agent",
    provider="groq",
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    max_tokens=2500,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=259200,  # 72h
)

# ══════════════════════════════════════════════════════════════════════════════
# MIGRATION VERS OLLAMA CLOUD PRO ($20/mois)
# Tous les modèles Groq ci-dessus seront remplacés par Ollama Cloud Pro.
# Changer provider="groq" → provider="ollama" + model selon table ci-dessous.
#
# Node                       Groq actuel (free)                     Ollama futur ($20/mois)
# ─────────────────────────  ─────────────────────────────────────  ──────────────────────────
# intent_classifier          llama-3.3-70b-versatile                gpt-oss:120b
# semantic_node              llama-3.3-70b-versatile (ex llama-4-scout, retire 2026-07-28)  gemini-3-flash-preview
# day_planner                llama-3.3-70b-versatile (ex llama-4-scout, retire 2026-07-28)  gpt-oss:120b
# recommendation_response    llama-3.3-70b-versatile (ex llama-4-scout, retire 2026-07-28)  gpt-oss:120b
# final_response             llama-3.3-70b-versatile                gpt-oss:120b
# ranking                    llama-3.1-8b-instant                   gpt-oss:120b
# ══════════════════════════════════════════════════════════════════════════════

