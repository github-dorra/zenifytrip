"""
Test du sous-pipeline informatif : information_node → informative_response_node.

Phase 1 — Routage (Python pur, 0 LLM) : vérifie que chaque question est classifiée
           dans le bon subtype après l'Option A (dynamic_factual par défaut).

Phase 2 — Réponse LLM complète (Gemini) : vérifie la qualité, le style et la langue
           des réponses générées par Agent 3.

Usage : python -m app.test_information_pipeline
"""
import io
import json
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.nodes.conversation.information_node import (
    InformationNode,
    _detect_subtype,
)
from app.nodes.conversation.informative_response_node import InformativeResponseNode

# ── couleurs terminal ────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

info_node     = InformationNode()
response_node = InformativeResponseNode()

phase1_results = []
phase2_results = []


# ════════════════════════════════════════════════════════════════════════════════
# PHASE 1 — Routage pur Python (0 LLM)
# ════════════════════════════════════════════════════════════════════════════════

def check_subtype(question: str, expected: str, label: str = ""):
    """Appelle _detect_subtype directement — rapide, 0 LLM."""
    msg_lower = question.lower()
    actual = _detect_subtype(
        msg_lower=msg_lower,
        last_candidates=[],
        availability_result=None,
        booking_anchors=None,
        profile_data=None,
    )
    ok = actual == expected
    icon = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
    detail = label or question[:60]
    print(f"  {icon}  [{actual:<18}]  {detail}")
    if not ok:
        print(f"           {RED}→ attendu : {expected}{RESET}")
    phase1_results.append((detail, ok))
    return ok


print(f"\n{BOLD}{'═'*70}{RESET}")
print(f"{BOLD}  PHASE 1 — Détection de subtype (Python pur, 0 LLM){RESET}")
print(f"{BOLD}{'═'*70}{RESET}")

# --- Questions qui étaient "factual" avant Option A (doivent être dynamic_factual maintenant)
print(f"\n{CYAN}→ Questions TOURISTIQUES (étaient factual, doivent être dynamic_factual){RESET}")
check_subtype("quelles sont les mosquées à visiter à Monastir ?",              "dynamic_factual", "mosquées Monastir")
check_subtype("le musée le plus célèbre à visiter à Kairouan",                 "dynamic_factual", "musée Kairouan")
check_subtype("meilleure plage près de Sfax ?",                                "dynamic_factual", "plage Sfax")
check_subtype("code vestimentaire pour visiter Dougga",                        "dynamic_factual", "code vestimentaire Dougga")
check_subtype("comment marchander dans les souks de Tunis ?",                  "dynamic_factual", "marchander souks Tunis")
check_subtype("les traditions du ramadan en Tunisie",                          "dynamic_factual", "traditions ramadan")
check_subtype("est-ce qu'on peut entrer dans la grande mosquée de Kairouan ?", "dynamic_factual", "accès mosquée Kairouan")
check_subtype("balade en chameau à Douz, combien de temps ?",                  "dynamic_factual", "chameau Douz")

# --- Questions déjà dynamic_factual avant (ne doivent pas régresser)
print(f"\n{CYAN}→ Questions LIVE (étaient déjà dynamic_factual, doivent rester){RESET}")
check_subtype("documents pour entrer en Tunisie avec un passeport français",   "dynamic_factual", "visa Français")
check_subtype("horaires du musée du Bardo",                                    "dynamic_factual", "horaires Bardo")
check_subtype("prix d'entrée à Dougga",                                        "dynamic_factual", "prix Dougga")
check_subtype("festival de Carthage 2026 dates",                               "dynamic_factual", "festival Carthage")

# --- Questions météo (doivent rester weather)
print(f"\n{CYAN}→ Questions MÉTÉO (doivent rester weather){RESET}")
check_subtype("quel temps fait-il à Djerba ?",                                 "weather",         "météo Djerba")
check_subtype("est-ce qu'on peut se baigner en octobre à Hammamet ?",          "weather",         "baignade octobre")
check_subtype("quels vêtements prévoir pour Tunis en janvier ?",               "weather",         "vêtements Tunis janvier")

# --- Questions booking (doivent rester booking_info si contexte dispo)
print(f"\n{CYAN}→ Questions BOOKING sans contexte (doivent tomber en dynamic_factual){RESET}")
check_subtype("mon vol est à quelle heure ?",                                  "dynamic_factual", "mon vol (sans contexte)")
check_subtype("quel est mon hôtel ?",                                          "dynamic_factual", "mon hôtel (sans contexte)")


# ════════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Réponse LLM complète
# ════════════════════════════════════════════════════════════════════════════════

SCENARIOS = [
    {
        "label": "S1 — Mosquées à Monastir (touristique, dynamic_factual, Tavily attendu)",
        "state": {
            "user_message":      "quelles sont les mosquées à visiter à Monastir ?",
            "normalized_message":"quelles sont les mosquées à visiter à monastir ?",
            "intent_result":     {"primary_intent": "travel_question", "language": "fr"},
            "merged_context":    {"destination": "Monastir"},
        },
        "checks": [
            ("final_answer non vide",          lambda r: bool(r.get("final_answer"))),
            ("response_mode=informative",      lambda r: (r.get("response_agent_result") or {}).get("response_mode") == "informative"),
            ("confidence ≥ 0.55",              lambda r: float((r.get("response_agent_result") or {}).get("confidence", 0)) >= 0.55),
            ("mentionne 'mosquée'",            lambda r: "mosqu" in (r.get("final_answer") or "").lower()),
        ],
    },
    {
        "label": "S2 — Visa pour ressortissant français (dynamic_factual, Tavily attendu)",
        "state": {
            "user_message":      "quels documents faut-il pour entrer en Tunisie avec un passeport français ?",
            "normalized_message":"quels documents faut-il pour entrer en tunisie avec un passeport français ?",
            "intent_result":     {"primary_intent": "travel_question", "language": "fr"},
            "merged_context":    {"destination": "Tunisie"},
        },
        "checks": [
            ("final_answer non vide",          lambda r: bool(r.get("final_answer"))),
            ("confidence ≥ 0.55",              lambda r: float((r.get("response_agent_result") or {}).get("confidence", 0)) >= 0.55),
            ("mentionne 'visa' ou 'passeport'",lambda r: any(w in (r.get("final_answer") or "").lower() for w in ["visa", "passeport", "passport"])),
        ],
    },
    {
        "label": "S3 — Musée célèbre à Kairouan (touristique, dynamic_factual)",
        "state": {
            "user_message":      "quel est le musée le plus célèbre à visiter à Kairouan ?",
            "normalized_message":"quel est le musée le plus célèbre à visiter à kairouan ?",
            "intent_result":     {"primary_intent": "travel_question", "language": "fr"},
            "merged_context":    {"destination": "Kairouan"},
        },
        "checks": [
            ("final_answer non vide",          lambda r: bool(r.get("final_answer"))),
            ("mentionne 'musée' ou 'Kairouan'",lambda r: any(w in (r.get("final_answer") or "").lower() for w in ["musée", "musee", "kairouan", "islamic", "raqqada"])),
        ],
    },
    {
        "label": "S4 — Horaires mosquée Habib Bourguiba (live, dynamic_factual)",
        "state": {
            "user_message":      "quels sont les horaires de visite de la mosquée Habib Bourguiba ?",
            "normalized_message":"quels sont les horaires de visite de la mosquée habib bourguiba ?",
            "intent_result":     {"primary_intent": "travel_question", "language": "fr"},
            "merged_context":    {"destination": "Monastir"},
        },
        "checks": [
            ("final_answer non vide",          lambda r: bool(r.get("final_answer"))),
            ("mentionne horaire ou visite",    lambda r: any(w in (r.get("final_answer") or "").lower() for w in ["heure", "horaire", "visite", "ouvert", "matin", "h"])),
            ("response_mode=informative",      lambda r: (r.get("response_agent_result") or {}).get("response_mode") == "informative"),
        ],
    },
    {
        "label": "S5 — Question en arabe : أين أجمل شواطئ المنستير",
        "state": {
            "user_message":      "أين أجمل شواطئ المنستير ؟",
            "normalized_message":"أين أجمل شواطئ المنستير ؟",
            "intent_result":     {"primary_intent": "travel_question", "language": "ar"},
            "merged_context":    {"destination": "Monastir"},
        },
        "checks": [
            ("final_answer non vide",          lambda r: bool(r.get("final_answer"))),
            ("response non vide ≥ 20 chars",   lambda r: len(r.get("final_answer") or "") >= 20),
        ],
    },
]


def run_pipeline(state: dict) -> dict:
    """Enchaîne information_node → informative_response_node."""
    info_result   = info_node.run(state)
    enriched      = {**state, **info_result}
    final_result  = response_node.run(enriched)
    return {**enriched, **final_result}


print(f"\n{BOLD}{'═'*70}{RESET}")
print(f"{BOLD}  PHASE 2 — Réponse LLM complète (Gemini){RESET}")
print(f"{BOLD}{'═'*70}{RESET}")

for sc in SCENARIOS:
    label = sc["label"]
    print(f"\n{BOLD}{'─'*70}{RESET}")
    print(f"{BOLD}  {label}{RESET}")
    print(f"{'─'*70}")

    try:
        result = run_pipeline(sc["state"])
    except Exception as exc:
        print(f"  {RED}❌ CRASH : {exc}{RESET}")
        phase2_results.append((label, False))
        continue

    # Affichage détaillé
    info_ctx    = result.get("information_context") or {}
    subtype     = info_ctx.get("subtype", "?")
    has_web     = (info_ctx.get("resolved_data") or {}).get("has_web_data", "N/A")
    answer      = result.get("final_answer") or ""
    agent_res   = result.get("response_agent_result") or {}
    confidence  = agent_res.get("confidence", "?")

    print(f"  subtype     : {CYAN}{subtype}{RESET}")
    print(f"  has_web_data: {has_web}")
    print(f"  confidence  : {confidence}")
    print(f"  réponse     :\n    {YELLOW}{answer[:300]}{RESET}")

    # Évaluation des checks
    sc_pass = True
    for check_label, check_fn in sc["checks"]:
        try:
            ok = check_fn(result)
        except Exception:
            ok = False
        icon = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
        print(f"  {icon}  {check_label}")
        if not ok:
            sc_pass = False

    phase2_results.append((label, sc_pass))


# ════════════════════════════════════════════════════════════════════════════════
# RÉSUMÉ FINAL
# ════════════════════════════════════════════════════════════════════════════════

p1_pass = sum(1 for _, ok in phase1_results if ok)
p1_total = len(phase1_results)
p2_pass = sum(1 for _, ok in phase2_results if ok)
p2_total = len(phase2_results)

print(f"\n{BOLD}{'═'*70}{RESET}")
print(f"{BOLD}  RÉSUMÉ{RESET}")
print(f"{'═'*70}")
print(f"  Phase 1 (routage)  : {GREEN if p1_pass==p1_total else RED}{p1_pass}/{p1_total} PASS{RESET}")
print(f"  Phase 2 (LLM)      : {GREEN if p2_pass==p2_total else RED}{p2_pass}/{p2_total} PASS{RESET}")

for name, ok in phase1_results + phase2_results:
    icon = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
    print(f"  {icon}  {name}")

total_pass = p1_pass + p2_pass
total = p1_total + p2_total
rate = total_pass / total * 100 if total else 0
print(f"\n  {BOLD}GLOBAL : {total_pass}/{total} ({rate:.0f}%){RESET}")
print(f"{'═'*70}\n")

sys.exit(0 if total_pass == total else 1)
