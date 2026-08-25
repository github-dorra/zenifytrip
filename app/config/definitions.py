"""
AI Agent definitions — only the agents that still require LLM reasoning.
The other data-fetching agents (flights, accommodation, activities, logistics)
are now pure API services and no longer need AI.

Fournisseur actuel : Gemini 3.1 Flash Lite (Google AI Studio — gratuit, 15 RPM, 250K TPM)
Migration effectuée le 2026-07-28 depuis Groq (llama-3.3-70b-versatile) vers gemini-3.1-flash-lite.
Raison : quota Groq TPD (100K tokens/jour) insuffisant pour le développement.
Projet AI Studio : gen-lang-client-0242501178 (zenify) — gemini-2.0-flash quota=0 sur ce compte.
"""
from app.nodes.core.Base_node import NodeConfig

_GEMINI_MODEL = "gemini-3.1-flash-lite"   # 15 RPM, 250K TPM — free tier AI Studio (gen-lang-client-0242501178)
# gemini-2.0-flash quota=0 sur ce compte | gemini-2.5-flash-lite=10 RPM | gemini-3.1-flash-lite=15 RPM (meilleur)

INTENT_CLASSIFIER_CONFIG = NodeConfig(
    name="intent_classifier",
    node_type="comprehension",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.0,
    max_tokens=800,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=3600,
)

SEMANTIC_CONFIG = NodeConfig(
    name="semantic_agent",
    node_type="comprehension",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.0,
    max_tokens=800,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=3600,
)

RANKING_CONFIG = NodeConfig(
    name="ranking",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.2,
    max_tokens=800,
    response_format="json",
    cache_enabled=False,
)

DAY_PLANNER_CONFIG = NodeConfig(
    name="day_planner",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.3,
    max_tokens=3000,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=1800,
)

# Agent clarification (chemin ask_clarification → final_response_node)
# Agent informatif (chemin information_node → final_response_node)
RESPONSE_CONFIG = NodeConfig(
    name="response",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.4,
    max_tokens=2500,
    response_format="json",
    cache_enabled=False,
)

# Agent 3 — réponse informative expert (travel_question / booking_question)
# Prompt spécialisé : données web Tavily (dynamic_factual) + booking + connaissance Tunisie (stable factual)
INFORMATIVE_RESPONSE_CONFIG = NodeConfig(
    name="informative_response",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.3,
    max_tokens=1500,
    response_format="json",
    cache_enabled=False,
)

# Agent 2 — présentation des recommandations (chemin data_merger → recommendation_response_node)
RECOMMENDATION_RESPONSE_CONFIG = NodeConfig(
    name="recommendation_response",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.4,
    max_tokens=3000,
    response_format="json",
    cache_enabled=False,
)

ORCHESTRATOR_CONFIG = NodeConfig(
    name="orchestrator",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.0,
    max_tokens=600,
    response_format="json",
    cache_enabled=False,
)

RESTAURANT_B_CONFIG = NodeConfig(
    name="restaurant_node_b",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.3,
    max_tokens=2500,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=259200,  # 72h
)

RESTAURANT_C_CONFIG = NodeConfig(
    name="restaurant_node_c",
    node_type="llm_agent",
    provider="gemini",
    model=_GEMINI_MODEL,
    temperature=0.3,
    max_tokens=2500,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=259200,  # 72h
)

# ══════════════════════════════════════════════════════════════════════════════
# HISTORIQUE DES MIGRATIONS
#
# Groq (dev, 2026-05 → 2026-07)         llama-3.3-70b-versatile        100K TPD — insuffisant dev
# Gemini 3.1 Flash Lite (2026-07-28 →)  gemini-3.1-flash-lite          15 RPM, 250K TPM, gratuit AI Studio
#
# Migration future → Ollama Cloud Pro ($20/mois) si production multi-utilisateurs
# Node                       Gemini actuel (free)    Ollama futur ($20/mois)
# ─────────────────────────  ──────────────────────  ──────────────────────────
# intent_classifier          gemini-2.0-flash        gpt-oss:120b
# semantic_node              gemini-2.0-flash        gemini-3-flash-preview
# day_planner                gemini-2.0-flash        gpt-oss:120b
# recommendation_response    gemini-2.0-flash        gpt-oss:120b
# final_response             gemini-2.0-flash        gpt-oss:120b
# ranking                    gemini-2.0-flash        gpt-oss:120b  (Python pur, config secours)
# ══════════════════════════════════════════════════════════════════════════════
