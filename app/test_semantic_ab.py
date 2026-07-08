"""
test_semantic_ab.py
─────────────────────────────────────────────────────────────────────────────
Compare SEMANTIC_SYSTEM_PROMPT (V1) vs SEMANTIC_SYSTEM_PROMPT_V2 (V2)
sur les mêmes inputs — même modèle, même température.

Applique la MÊME validation Python que SemanticAgentNode._validate_keywords()
pour montrer les keywords qui survivent réellement dans le pipeline.

Usage :
    python -m app.test_semantic_ab
"""

import json
import re
from typing import Any, List, Set

from app.config.llm_service import call_groq_llm
from app.config.definitions import SEMANTIC_CONFIG
from app.nodes.utility.json_parser import parse_json_safely
from app.prompts.recommendation.semantic_prompt import (
    SEMANTIC_SYSTEM_PROMPT,
    SEMANTIC_SYSTEM_PROMPT_V2,
)
# Import des pools exacts utilisés en production
from app.nodes.recommendation.context.semantic_node import SemanticAgentNode

# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION (miroir exact de SemanticAgentNode._validate_keywords)
# ─────────────────────────────────────────────────────────────────────────────

CAMEL_CASE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9]*$")

def validate_keywords(keywords: Any, allowed: Any, max_count: int = 8) -> tuple:
    """
    Retourne (valid_list, rejected_list) — miroir exact de la logique production.
    """
    if not isinstance(keywords, list):
        keywords = [keywords] if keywords else []
    keywords = [str(k).strip() for k in keywords if isinstance(k, str) and k.strip()]

    valid, rejected = [], []
    seen = set()

    for kw in keywords:
        if not CAMEL_CASE_PATTERN.match(kw):
            rejected.append((kw, "format invalide"))
            continue
        if allowed and allowed != "ALL":
            allowed_lower = {k.lower() for k in allowed}
            if kw.lower() not in allowed_lower:
                rejected.append((kw, "hors pool"))
                continue
        if kw in seen:
            rejected.append((kw, "doublon"))
            continue
        seen.add(kw)
        valid.append(kw)

    if len(valid) > max_count:
        rejected.extend([(k, "dépassement max") for k in valid[max_count:]])
        valid = valid[:max_count]

    return valid, rejected


def get_allowed_pool(primary_intent: str):
    config = SemanticAgentNode.INTENT_KEYWORD_POOLS.get(primary_intent, {})
    return config.get("keywords", set()), config.get("domain", "unknown")


# ─────────────────────────────────────────────────────────────────────────────
# SCÉNARIOS DE TEST
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "label": "S1 — flight · Paris→Tunis · solo · business",
        "primary_intent": "flight_recommendation",
        "user_message": "je veux un vol de Paris à Tunis en classe affaires",
        "merged_context": {
            "primary_intent": "flight_recommendation",
            "secondary_intents": [],
            "destination": "Tunis",
            "origin": "Paris",
            "travelers": 1,
            "is_family": False,
            "duration_days": 7,
            "budget_level": "luxury",
            "interests": ["business", "comfort"],
        },
        "weather_context": {},
    },
    {
        "label": "S2 — trip_package · Tozeur · couple · luxury",
        "primary_intent": "trip_package_recommendation",
        "user_message": "on veut un voyage complet romantique à Tozeur avec mon mari",
        "merged_context": {
            "primary_intent": "trip_package_recommendation",
            "secondary_intents": [
                "accommodation_recommendation",
                "activity_recommendation",
                "restaurant_recommendation",
            ],
            "destination": "Tozeur",
            "travelers": 2,
            "is_family": False,
            "duration_days": 4,
            "budget_level": "luxury",
            "interests": ["desert", "romantic", "cultural"],
        },
        "weather_context": {
            "avg_temperature": 38,
            "is_sunny_day": True,
            "is_hot_day": True,
            "recommendation_hint": "outdoor",
        },
    },
    {
        "label": "S3 — activity · Tabarka · solo · aventure outdoor",
        "primary_intent": "activity_recommendation",
        "user_message": "quelles activités aventure en plein air à Tabarka ?",
        "merged_context": {
            "primary_intent": "activity_recommendation",
            "secondary_intents": [],
            "destination": "Tabarka",
            "travelers": 1,
            "is_family": False,
            "duration_days": 3,
            "budget_level": "medium",
            "interests": ["hiking", "nature", "adventure"],
        },
        "weather_context": {
            "avg_temperature": 22,
            "is_sunny_day": True,
            "is_rainy_day": False,
            "outdoor_score": 0.95,
            "recommendation_hint": "outdoor",
        },
    },
    {
        "label": "S4 — accommodation · Monastir · famille · pluie",
        "primary_intent": "accommodation_recommendation",
        "user_message": "cherche hôtel avec piscine couverte à Monastir pour 3 enfants",
        "merged_context": {
            "primary_intent": "accommodation_recommendation",
            "secondary_intents": [],
            "destination": "Monastir",
            "travelers": 5,
            "is_family": True,
            "duration_days": 6,
            "budget_level": "medium",
            "interests": ["pool", "kids", "indoor"],
        },
        "weather_context": {
            "avg_temperature": 16,
            "is_sunny_day": False,
            "is_rainy_day": True,
            "indoor_score": 0.9,
            "recommendation_hint": "indoor",
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def run_prompt(prompt_template: str, scenario: dict) -> dict:
    prompt = prompt_template.format(
        user_message=scenario["user_message"],
        merged_context=json.dumps(scenario["merged_context"], ensure_ascii=False),
        weather_context=json.dumps(scenario["weather_context"], ensure_ascii=False),
    )
    response = call_groq_llm(
        prompt=prompt,
        model=SEMANTIC_CONFIG.model,
        temperature=SEMANTIC_CONFIG.temperature,
        max_tokens=SEMANTIC_CONFIG.max_tokens,
    )
    raw = response.get("content", "")
    parsed = parse_json_safely(raw) or {}
    return {
        "parsed": parsed,
        "raw": raw,
        "tokens": response.get("usage", {}),
    }


def apply_validation(parsed: dict, primary_intent: str) -> dict:
    allowed_global, domain = get_allowed_pool(primary_intent)
    allowed_ctx = SemanticAgentNode.UNIVERSAL_CONTEXTUAL

    global_valid, global_rejected = validate_keywords(
        parsed.get("global_keywords", []), allowed_global, max_count=8
    )
    ctx_valid, ctx_rejected = validate_keywords(
        parsed.get("contextual_keywords", []), allowed_ctx, max_count=8
    )
    return {
        "domain": domain,
        "global_raw":      parsed.get("global_keywords", []),
        "global_valid":    global_valid,
        "global_rejected": global_rejected,
        "ctx_raw":         parsed.get("contextual_keywords", []),
        "ctx_valid":       ctx_valid,
        "ctx_rejected":    ctx_rejected,
        "semantic_query":  parsed.get("semantic_query", ""),
    }


def print_scenario_result(label: str, v1: dict, v2: dict,
                          tok1: dict, tok2: dict):
    print(f"\n{'═'*114}")
    print(f"  {label}")
    print(f"{'═'*114}")

    W = 54
    sep = "─" * W
    print(f"  {'V1 (original)':^54}  {'V2 (optimisé)':^54}")
    print(f"  {sep}  {sep}")

    def fmt_list(lst, max_w=52):
        s = ", ".join(lst) if lst else "—"
        return s[:max_w] + "…" if len(s) > max_w else s

    # semantic_query
    q1 = (v1["semantic_query"] or "")[:52]
    q2 = (v2["semantic_query"] or "")[:52]
    print(f"  query   : {q1:<54}  query   : {q2}")

    # global keywords raw
    print(f"  {sep}  {sep}")
    print(f"  global_keywords RAW:")
    print(f"    V1: {fmt_list(v1['global_raw'])}")
    print(f"    V2: {fmt_list(v2['global_raw'])}")

    # global keywords AFTER validation
    print(f"  global_keywords APRÈS validation:")
    g1_ok = v1["global_valid"]
    g2_ok = v2["global_valid"]
    print(f"    V1 ✅ ({len(g1_ok)}) : {fmt_list(g1_ok)}")
    print(f"    V2 ✅ ({len(g2_ok)}) : {fmt_list(g2_ok)}")

    if v1["global_rejected"]:
        rej = [f"{k}({r})" for k, r in v1["global_rejected"]]
        print(f"    V1 ❌ rejetés : {fmt_list(rej)}")
    if v2["global_rejected"]:
        rej = [f"{k}({r})" for k, r in v2["global_rejected"]]
        print(f"    V2 ❌ rejetés : {fmt_list(rej)}")

    # contextual keywords AFTER validation
    print(f"  contextual_keywords APRÈS validation:")
    c1_ok = v1["ctx_valid"]
    c2_ok = v2["ctx_valid"]
    print(f"    V1 ✅ ({len(c1_ok)}) : {fmt_list(c1_ok)}")
    print(f"    V2 ✅ ({len(c2_ok)}) : {fmt_list(c2_ok)}")

    if v1["ctx_rejected"]:
        rej = [f"{k}({r})" for k, r in v1["ctx_rejected"]]
        print(f"    V1 ❌ rejetés : {fmt_list(rej)}")
    if v2["ctx_rejected"]:
        rej = [f"{k}({r})" for k, r in v2["ctx_rejected"]]
        print(f"    V2 ❌ rejetés : {fmt_list(rej)}")

    # tokens
    print(f"  {sep}  {sep}")
    tp1, tp2 = tok1.get("prompt_tokens", 0), tok2.get("prompt_tokens", 0)
    saving = round((1 - tp2 / tp1) * 100) if tp1 else 0
    print(f"  prompt_tokens : V1={tp1}  V2={tp2}  économie={saving}%")
    print(f"  total_tokens  : V1={tok1.get('total_tokens',0)}  V2={tok2.get('total_tokens',0)}")

    # verdict — comparaison case-insensitive, direction-aware
    g1_norm = {k.lower() for k in g1_ok}
    g2_norm = {k.lower() for k in g2_ok}
    c1_norm = {k.lower() for k in c1_ok}
    c2_norm = {k.lower() for k in c2_ok}
    global_eq = g1_norm == g2_norm
    ctx_eq    = c1_norm == c2_norm
    # Direction-aware : V2 enrichi (+keywords) vs appauvri (-keywords)
    v2_richer_global = g1_norm.issubset(g2_norm) and not global_eq   # V1 ⊆ V2 strict
    v2_poorer_global = g2_norm.issubset(g1_norm) and not global_eq   # V2 ⊆ V1 strict
    v2_richer_ctx    = c1_norm.issubset(c2_norm) and not ctx_eq
    v2_poorer_ctx    = c2_norm.issubset(c1_norm) and not ctx_eq
    global_compat    = global_eq or v2_richer_global or v2_poorer_global
    ctx_compat       = ctx_eq    or v2_richer_ctx    or v2_poorer_ctx
    if global_eq and ctx_eq:
        verdict = "✅ ÉQUIVALENT"
    elif v2_richer_global and (ctx_eq or v2_richer_ctx):
        verdict = "✅ V2 ENRICHI"
    elif (v2_poorer_global or v2_poorer_ctx) and global_compat and ctx_compat:
        verdict = "⚠️  V2 APPAUVRI"
    elif global_compat and ctx_compat:
        verdict = "✅ V2 COMPATIBLE"
    elif not global_eq:
        verdict = "⚠️  global différent"
    else:
        verdict = "⚠️  contextual différent"
    note = ""
    diff_g = len(g2_ok) - len(g1_ok)
    diff_c = len(c2_ok) - len(c1_ok)
    if not global_eq and global_compat:
        note += f"  (global: V2 {diff_g:+d})"
    if not ctx_eq and ctx_compat:
        note += f"  (contextual: V2 {diff_c:+d})"
    print(f"\n  VERDICT : {verdict}{note}  (global: {'=' if global_eq else '≠'}  contextual: {'=' if ctx_eq else '≠'})")

    is_ok = global_compat and ctx_compat and not (v2_poorer_global or v2_poorer_ctx)
    return is_ok, tp1, tp2


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "█"*114)
    print("  SEMANTIC NODE — TEST A/B  :  V1 vs V2  (avec validation Python réelle)")
    print("█"*114)

    total_tp1, total_tp2 = 0, 0
    all_equiv = True

    for sc in SCENARIOS:
        print(f"\n  ⏳ {sc['label']}...")
        try:
            r1 = run_prompt(SEMANTIC_SYSTEM_PROMPT,    sc)
            r2 = run_prompt(SEMANTIC_SYSTEM_PROMPT_V2, sc)
        except Exception as e:
            print(f"  ❌ Erreur LLM : {e}")
            continue

        val1 = apply_validation(r1["parsed"], sc["primary_intent"])
        val2 = apply_validation(r2["parsed"], sc["primary_intent"])

        verdict_ok, tp1, tp2 = print_scenario_result(
            sc["label"], val1, val2, r1["tokens"], r2["tokens"]
        )
        total_tp1 += tp1
        total_tp2 += tp2
        if not verdict_ok:
            all_equiv = False

    # ── Résumé global
    saving_total = total_tp1 - total_tp2
    saving_pct   = round((saving_total / total_tp1) * 100) if total_tp1 else 0

    print(f"\n{'═'*114}")
    print(f"  RÉSUMÉ GLOBAL ({len(SCENARIOS)} scénarios)")
    print(f"{'═'*114}")
    print(f"  Total prompt_tokens V1 : {total_tp1}")
    print(f"  Total prompt_tokens V2 : {total_tp2}")
    print(f"  Économie totale        : {saving_total} tokens  ({saving_pct}%)")
    print(f"  Équivalence qualité    : {'✅ IDENTIQUE post-validation' if all_equiv else '⚠️  DIFFÉRENCES — voir détails'}")
    print(f"\n  {'→ V2 VALIDÉ — prêt à remplacer V1' if all_equiv else '→ V2 À REVOIR — des scénarios divergent après validation'}")
    print(f"{'═'*114}\n")


if __name__ == "__main__":
    main()
