"""
AI Agent definitions — only the agents that still require LLM reasoning.
The other data-fetching agents (flights, accommodation, activities, logistics)
are now pure API services and no longer need AI.
"""
from app.nodes.core.Base_node import NodeConfig



INTENT_CLASSIFIER_CONFIG = NodeConfig(
    name="intent_classifier",
    node_type="comprehension",
    provider="groq",#ollama
    model="llama-3.3-70b-versatile",#gpt-oss:120b
    temperature=0.0,
    max_tokens=800,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=3600,
)

SEMANTIC_CONFIG= NodeConfig(
                name="semantic_agent",
                node_type="comprehension",
                provider="ollama",
                model= "gemini-3-flash-preview", #deepseek-v4-pro",
                temperature=0.4,
                max_tokens=2000,
                response_format="json",
                cache_enabled=True,
                cache_ttl_seconds=3600,
)

ORCHESTRATOR_CONFIG = NodeConfig(
    name="orchestrator",
    node_type="llm_agent",
    provider="ollama",
    model="gpt-oss:120b",
    temperature=0.1,
    max_tokens=1500,
    response_format="json",
    cache_enabled=False,
)


RANKING_CONFIG = NodeConfig(
    name="ranking",
    node_type="llm_agent",
    provider="ollama",
    model="gpt-oss:120b",
    temperature=0.2,
    max_tokens=2000,
    response_format="json",
    cache_enabled=False,
)


DAY_PLANNER_CONFIG = NodeConfig(
    name="day_planner",
    node_type="llm_agent",
    provider="ollama",
    model="gpt-oss:120b",
    temperature=0.3,
    max_tokens=3000,
    response_format=None,
    cache_enabled=False,
)


RESPONSE_CONFIG = NodeConfig(
    name="response",
    node_type="llm_agent",
    provider="ollama",
    model="gpt-oss:120b",
    temperature=0.5,
    max_tokens=3000,
    response_format=None,
    cache_enabled=False,
)

RESTAURANT_C_CONFIG = NodeConfig(
    name="restaurant_node_c",
    node_type="llm_agent",
    provider="groq",
    model="llama-3.3-70b-versatile",
    temperature=0.1,
    max_tokens=3000,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=259200,  # 72h
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

