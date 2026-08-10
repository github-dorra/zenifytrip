"""
OrchestratorNode — Hybrid (règles + LLM conditionnel)
=====================================================
Règles Python pour 80% des cas (intent simple, pas de voyage en cours).
LLM appelé uniquement quand le contexte est non-trivial :
  - trip_is_ongoing=True  (voyage actif → contraintes repas/anchors/dernier jour)
  - is_last_day=True      (fenêtre de temps réduite)
  - meal_plan non nul     (repas inclus → impact restaurant_node)
  - day_skeleton avec anchors (créneaux déjà occupés → exclure ou contraindre)

Retourne :
  requested_services       : list[str]
  orchestrator_constraints : dict par service (lus par chaque domain node)
  orchestrator_reasoning   : str trace (debug / rapport PFE)
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.nodes.core.Base_node import BaseNode
from app.config.definitions import ORCHESTRATOR_CONFIG
from app.prompts.recommendation.orchestrator_prompt import ORCHESTRATOR_PROMPT
from app.schemas.orchestrator_schema import OrchestratorOutput
from app.nodes.utility.json_parser import parse_json_safely

logger = logging.getLogger(__name__)

# ── Mapping intent → services de base (chemin règles — 80%) ──────────────────
INTENT_TO_SERVICES: Dict[str, List[str]] = {
    "accommodation_recommendation":  ["hotel_node"],
    "flight_recommendation":         ["flight_node"],
    "restaurant_recommendation":     ["restaurant_node"],
    "activity_recommendation":       ["activity_node"],
    "day_planning":                  ["hotel_node", "activity_node", "restaurant_node"],
    "trip_package_recommendation":   ["flight_node", "hotel_node", "activity_node", "restaurant_node"],
    "travel_question":   [],
    "booking_question":  [],
    "profile_update":    [],
    "feedback":          [],
    "greeting":          [],
    "unsupported":       [],
}

SERVICE_ORDER = ["flight_node", "hotel_node", "activity_node", "restaurant_node"]

# ── Café / pâtisserie / boire override ───────────────────────────────────────
# Keyword normalisé → establishment_types dans restaurant_collection
# Activé quand primary_intent==activity_recommendation mais le user veut
# un café, une pâtisserie ou un endroit pour boire (absents d'activities_collection)
_CAFE_TRIGGERS_MAP: Dict[str, List[str]] = {
    # ── Café / coffee ────────────────────────────────────────────────────────
    "cafe":          ["cafe"],   "cafes":         ["cafe"],
    "coffee":        ["cafe"],   "coffeeshop":    ["cafe"],
    "expresso":      ["cafe"],   "espresso":      ["cafe"],
    "cappuccino":    ["cafe"],   "latte":         ["cafe"],
    "nescafe":       ["cafe"],   "americano":     ["cafe"],
    "qahwa":         ["cafe"],   "kahwa":         ["cafe"],
    # ── Salon de thé / infusions ─────────────────────────────────────────────
    "salon":         ["cafe"],   "salons":        ["cafe"],
    "infusion":      ["cafe"],   "tisane":        ["cafe"],
    "menthe":        ["cafe"],   "verveine":      ["cafe"],
    "lipton":        ["cafe"],   "karkade":       ["cafe"],
    # ── Bar / Boire ──────────────────────────────────────────────────────────
    "bar":           ["bar"],    "bars":          ["bar"],
    "boire":         ["cafe", "bar"],
    "boisson":       ["cafe", "bar"],   "boissons":    ["cafe", "bar"],
    "jus":           ["cafe", "bar"],   "sirop":       ["cafe", "bar"],
    "limonade":      ["cafe", "bar"],   "smoothie":    ["cafe", "bar"],
    "cocktail":      ["cafe", "bar"],   "mocktail":    ["cafe", "bar"],
    "boga":          ["cafe", "bar"],   "softdrink":   ["cafe", "bar"],
    "verre":         ["cafe", "bar"],   "verres":      ["cafe", "bar"],
    "brasserie":     ["cafe", "bar"],
    # ── Terrasse / rooftop / shisha ──────────────────────────────────────────
    "terrasse":      ["cafe", "bar"],   "terrace":     ["cafe", "bar"],
    "rooftop":       ["cafe", "bar"],   "lounge":      ["cafe", "bar"],
    "toit":          ["cafe", "bar"],   "exterieur":   ["cafe", "bar"],
    "dehors":        ["cafe", "bar"],   "pleinair":    ["cafe", "bar"],
    "shisha":        ["cafe", "bar"],   "chicha":      ["cafe", "bar"],
    "nargile":       ["cafe", "bar"],   "narguile":    ["cafe", "bar"],
    "hookah":        ["cafe", "bar"],   "arguileh":    ["cafe", "bar"],
    # ── Pâtisserie / desserts ────────────────────────────────────────────────
    "patisserie":    ["dessert"],       "patisseries": ["dessert"],
    "gateau":        ["dessert"],       "gateaux":     ["dessert"],
    "dessert":       ["dessert"],       "desserts":    ["dessert"],
    "glace":         ["dessert"],       "glaces":      ["dessert"],
    "sorbet":        ["dessert"],       "sorbets":     ["dessert"],
    "crepe":         ["dessert"],       "crepes":      ["dessert"],
    "macaron":       ["dessert"],       "macarons":    ["dessert"],
    "boulangerie":   ["dessert"],       "boulangeries":["dessert"],
    "viennoiserie":  ["dessert"],       "croissant":   ["dessert"],
    "brioche":       ["dessert"],
    # ── Pâtisseries tunisiennes ──────────────────────────────────────────────
    "makroudh":      ["dessert"],       "makrouth":    ["dessert"],
    "baklawa":       ["dessert"],       "baklava":     ["dessert"],
    "zlabia":        ["dessert"],       "bambalouni":  ["dessert"],
    "mlawi":         ["dessert"],       "msemen":      ["dessert"],
    "mlewi":         ["dessert"],       "cornet":      ["dessert"],
    "samsa":         ["dessert"],       "yo":          ["dessert"],
    "bsissa":        ["dessert"],
}

# Regex pour split camelCase sémantique : "coffeeShop" → ["coffee", "shop"]
_CAMEL_RE = re.compile(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z]|$)")
# Tokenisation message normalisé
_WORD_RE_ORCH = re.compile(r"[a-z0-9]+")


def _norm_kw(s: str) -> str:
    """Normalise un keyword : minuscules + suppression des diacritiques courants."""
    return (
        (s or "")
        .lower()
        .replace("é", "e").replace("è", "e").replace("ê", "e")
        .replace("à", "a").replace("â", "a").replace("û", "u")
        .replace("î", "i").replace("ô", "o").replace("ù", "u")
    )


def _split_kw(kw: str) -> List[str]:
    """Retourne les tokens d'un keyword, en splitant le camelCase si présent."""
    raw = _norm_kw(kw)
    if any(c.isupper() for c in kw):            # camelCase → split
        return [t.lower() for t in _CAMEL_RE.findall(kw) if len(t) > 1]
    return [raw] if raw else []


def _detect_cafe_etypes(state: Dict[str, Any], merged: Dict[str, Any]) -> Optional[List[str]]:
    """
    Analyse global_keywords, contextual_keywords, interests et normalized_message.
    Retourne la liste dédupliquée des establishment_types ciblés, ou None si aucun signal.
    """
    found: List[str] = []

    # 1. Keywords sémantiques (global + contextuel + intérêts)
    for kw in (
        list(state.get("global_keywords") or []) +
        list(state.get("contextual_keywords") or []) +
        list(merged.get("interests") or [])
    ):
        for token in _split_kw(kw):
            if token in _CAFE_TRIGGERS_MAP:
                found.extend(_CAFE_TRIGGERS_MAP[token])

    # 2. Message utilisateur normalisé — scan mot par mot
    msg_norm = _norm_kw(state.get("normalized_message") or state.get("user_message") or "")
    for token in _WORD_RE_ORCH.findall(msg_norm):
        if token in _CAFE_TRIGGERS_MAP:
            found.extend(_CAFE_TRIGGERS_MAP[token])

    if not found:
        return None

    # Dédupliquer en préservant l'ordre de priorité
    seen: set = set()
    result: List[str] = []
    for t in found:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


_NO_AIRPORT_CITIES = {
    "kairouan", "douz", "matmata", "zaghouan", "dougga", "tataouine", "gafsa",
    "makthar", "maktar", "le kef", "kef", "siliana", "jendouba", "ghardimaou",
}


class OrchestratorNode(BaseNode):
    """
    Hybrid orchestrator — règles Python pour les cas simples,
    LLM (Gemini 3.1 Flash Lite) pour les cas avec contexte de voyage actif.
    """

    def __init__(self):
        super().__init__(ORCHESTRATOR_CONFIG)

    # =========================================================
    # DÉCISION : appeler le LLM ou pas ?
    # =========================================================

    @staticmethod
    def _needs_llm(
        trip_is_ongoing: bool,
        is_last_day: bool,
        meal_plan: Optional[str],
        has_anchors: bool,
    ) -> bool:
        return trip_is_ongoing or is_last_day or bool(meal_plan) or has_anchors

    # =========================================================
    # CHEMIN RÈGLES — décision rapide sans LLM
    # =========================================================

    @staticmethod
    def _rules_decision(
        primary_intent: str,
        secondary_intents: List[str],
        suggestion_mode: str,
        destination: Optional[str],
        origin: Optional[str],
    ) -> Dict[str, Any]:
        base: set = set(INTENT_TO_SERVICES.get(primary_intent, []))

        for si in secondary_intents:
            for svc in INTENT_TO_SERVICES.get(si, []):
                base.add(svc)

        if primary_intent == "day_planning":
            base |= {"activity_node", "restaurant_node"}

        if primary_intent == "trip_package_recommendation" and destination:
            base = set(SERVICE_ORDER)

        if suggestion_mode == "exploratory" and base == {"hotel_node"}:
            base.add("activity_node")

        # Exclure flight pour destinations sans aéroport + pas d'origine
        if destination and destination.lower() in _NO_AIRPORT_CITIES and not origin:
            base.discard("flight_node")

        ordered = [s for s in SERVICE_ORDER if s in base]

        constraints: Dict[str, Dict] = {}
        if destination:
            for svc in ordered:
                constraints[svc] = {"destination": destination}

        return {
            "requested_services":       ordered,
            "orchestrator_constraints": constraints if constraints else None,
            "orchestrator_reasoning":   f"rules: intent={primary_intent} → {ordered}",
        }

    # =========================================================
    # CHEMIN LLM — contexte voyage actif
    # =========================================================

    def _llm_decision(self, state: Dict[str, Any]) -> Dict[str, Any]:
        trip_position   = state.get("trip_position")    or {}
        booking_anchors = state.get("booking_anchors")  or {}
        availability    = state.get("availability_result") or {}
        merged          = state.get("merged_context")   or {}
        intent          = state.get("intent_result")    or {}
        day_skeleton    = state.get("day_skeleton")
        user_type       = state.get("user_type", "native")

        trip_context = json.dumps({
            "trip_is_ongoing":     availability.get("trip_is_ongoing", False),
            "is_first_day":        trip_position.get("is_first_day", False),
            "is_last_day":         trip_position.get("is_last_day", False),
            "day_index":           trip_position.get("day_index"),
            "total_days":          trip_position.get("total_days"),
            "arrival_time":        trip_position.get("arrival_time"),
            "departure_time":      trip_position.get("departure_time"),
            "meal_plan":           booking_anchors.get("meal_plan"),
            "breakfast_included":  booking_anchors.get("breakfast_included"),
            "lunch_included":      booking_anchors.get("lunch_included"),
            "dinner_included":     booking_anchors.get("dinner_included"),
            "booked_services":     booking_anchors.get("booked_services", []),
            "hotel_name":          booking_anchors.get("hotel_name"),
            "days_remaining":      availability.get("days_remaining"),
            "user_type":           user_type,
        }, ensure_ascii=False)

        skeleton_text = json.dumps(day_skeleton, ensure_ascii=False) if day_skeleton else "null"

        intent_context = json.dumps({
            "primary_intent":    intent.get("primary_intent"),
            "secondary_intents": intent.get("secondary_intents", []),
            "action_type":       intent.get("action_type"),
            "language":          intent.get("language", "fr"),
            "destination":       merged.get("destination"),
            "origin":            merged.get("origin"),
            "budget_level":      merged.get("budget_level"),
            "duration_days":     merged.get("duration_days"),
            "interests":         merged.get("interests", []),
            "suggestion_mode":   state.get("suggestion_mode"),
        }, ensure_ascii=False)

        session_signals = json.dumps({
            "rejected_types": merged.get("rejected_types", []),
            "liked_types":    merged.get("liked_types", []),
        }, ensure_ascii=False)

        prompt = ORCHESTRATOR_PROMPT.format(
            trip_context=trip_context,
            day_skeleton=skeleton_text,
            intent_context=intent_context,
            session_signals=session_signals,
        )

        try:
            response = self.call_llm(prompt=prompt)
            raw = response.get("content", "")
            data = parse_json_safely(raw)
            output = OrchestratorOutput(**data)
        except Exception as e:
            self.logger.error(f"[OrchestratorNode] LLM error: {e} — fallback règles")
            return self._rules_decision(
                primary_intent=(state.get("intent_result") or {}).get("primary_intent", "unsupported"),
                secondary_intents=[],
                suggestion_mode=state.get("suggestion_mode", "exploratory"),
                destination=merged.get("destination"),
                origin=merged.get("origin"),
            )

        return {
            "requested_services":       output.requested_services,
            "orchestrator_constraints": output.constraints_per_service or None,
            "orchestrator_reasoning":   output.reasoning,
        }

    # =========================================================
    # RUN
    # =========================================================

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        intent          = state.get("intent_result")       or {}
        primary_intent  = intent.get("primary_intent", "unsupported")
        secondary       = intent.get("secondary_intents")  or []
        suggestion_mode = state.get("suggestion_mode", "exploratory")
        merged          = state.get("merged_context")      or {}
        destination     = merged.get("destination")
        origin          = merged.get("origin")

        availability    = state.get("availability_result") or {}
        trip_position   = state.get("trip_position")       or {}
        booking_anchors = state.get("booking_anchors")     or {}
        day_skeleton    = state.get("day_skeleton")

        trip_is_ongoing = bool(availability.get("trip_is_ongoing"))
        is_last_day     = bool(trip_position.get("is_last_day"))
        meal_plan       = booking_anchors.get("meal_plan") or ""
        has_anchors     = bool(
            day_skeleton and any(
                s.get("status") == "anchored"
                for d in (day_skeleton.get("days") or [])
                for s in (d.get("slots") or [])
            )
        )

        use_llm = self._needs_llm(trip_is_ongoing, is_last_day, meal_plan, has_anchors)

        self.logger.info(
            f"[OrchestratorNode] intent={primary_intent} | trip_ongoing={trip_is_ongoing} | "
            f"last_day={is_last_day} | meal_plan={meal_plan!r} | anchors={has_anchors} | "
            f"path={'LLM' if use_llm else 'rules'}"
        )

        if use_llm:
            result = self._llm_decision(state)
        else:
            result = self._rules_decision(
                primary_intent=primary_intent,
                secondary_intents=secondary,
                suggestion_mode=suggestion_mode,
                destination=destination,
                origin=origin,
            )

        # ── CAFÉ / PÂTISSERIE / BOIRE OVERRIDE ──────────────────────────────────
        # activity_recommendation + vocabulaire café/pâtisserie/boire
        # → activer restaurant_node avec establishment_types dynamique
        # (ces établissements sont dans restaurant_collection, PAS activities_collection)
        if (primary_intent == "activity_recommendation"
                and "restaurant_node" not in result["requested_services"]):
            detected_etypes = _detect_cafe_etypes(state, merged)
            if detected_etypes is not None:
                result = dict(result)
                result["requested_services"] = list(result["requested_services"]) + ["restaurant_node"]
                constraints = dict(result.get("orchestrator_constraints") or {})
                cafe_c = dict(constraints.get("restaurant_node") or {})
                if destination:
                    cafe_c["destination"] = destination
                cafe_c["establishment_types"] = detected_etypes
                constraints["restaurant_node"] = cafe_c
                result["orchestrator_constraints"] = constraints
                result["orchestrator_reasoning"] = (
                    (result.get("orchestrator_reasoning") or "") +
                    f" | cafe_override→+restaurant_node etypes={detected_etypes}"
                )

        self.logger.info(
            f"[OrchestratorNode] → services={result['requested_services']} | "
            f"constraints={list((result.get('orchestrator_constraints') or {}).keys())}"
        )
        return result
