import json
import os
import threading
import time
import uuid

from app.graph.builder import build_graph
from app.graph.state import build_initial_state
from app.services.activity_service.internal_activity_service import InternalActivityService
from app.services.session_manager import SessionManager, _trim_candidates
from app.config.settings import SESSION_MAX_CANDIDATES, SESSION_MAX_TURN_CHARS


# ── Fonctions utilitaires session ────────────────────────────────────────────

def extract_last_candidates(result: dict) -> list:
    """Extrait les 3-4 candidats présentés depuis ranked_results (format minimal)."""
    ranked = result.get("ranked_results") or []
    if not ranked:
        return []
    return _trim_candidates(ranked[:SESSION_MAX_CANDIDATES])


def extract_last_turn(result: dict, user_message: str) -> list:
    """Retourne les 2 derniers messages (user + assistant) tronqués à SESSION_MAX_TURN_CHARS."""
    turn = []
    if user_message:
        turn.append({"role": "user", "content": user_message[:SESSION_MAX_TURN_CHARS]})
    final_answer = result.get("final_answer") or ""
    if final_answer:
        turn.append({"role": "assistant", "content": final_answer[:SESSION_MAX_TURN_CHARS]})
    return turn


session_manager = SessionManager()

def main():
    graph = build_graph()

    # Pre-warm cache activités en arrière-plan — élimine le cold cache de 4.5s
    # sur la 1ère requête; n'affecte pas le démarrage (thread daemon)
    threading.Thread(
        target=InternalActivityService.pre_warm_cache,
        name="activities-prewarm",
        daemon=True,
    ).start()

    state = build_initial_state(
        user_message   = "",
        user_id= "df55d964-039d-4838-8e5e-352ce1708bd9",   #"2720b441-6e48-464f-880b-71dd2d4cdca5",
        session_id= str(uuid.uuid4()),
        conversation_id= str(uuid.uuid4()),
        travellerId="",
    )

    print("Assistant: Bonjour ! Où souhaitez-vous partir ?")

    user_id = state.get("user_id") or ""

    try:
        while True:
            user_message = input("\nUser: ").strip()
            if not user_message:
                print("Assistant: Please enter a message.")
                continue

            state["user_message"] = user_message

            # ── Chargement session depuis Redis (fallback si Redis down → {}) ──
            session = session_manager.load(user_id)
            if session.get("last_candidates") and not state.get("last_candidates"):
                state["last_candidates"] = session["last_candidates"]
            # weather_context : charger depuis Redis si absent et destination connue
            dest_hint = (
                session.get("destination")
                or (state.get("merged_context") or {}).get("destination")
            )
            if dest_hint and not state.get("weather_context"):
                cached_wx = session_manager.load_weather(dest_hint)
                if cached_wx:
                    state["weather_context"] = cached_wx

            # ── Streaming du graphe : squelette immédiat, réponse ensuite ──
            start = time.time()
            result = dict(state)          # accumulateur — équivalent du retour d'invoke()
            skeleton_shown = False

            for chunk in graph.stream(state, stream_mode="updates"):
                # chunk = {node_name: update_dict} — un par node terminé
                for node_name, update in chunk.items():
                    if not isinstance(update, dict):
                        continue

                    # Accumulation dans result (listes additives préservées)
                    for key, value in update.items():
                        if key in ("errors", "node_metrics"):
                            result[key] = (result.get(key) or []) + (value or [])
                        else:
                            result[key] = value

                    # ★ SQUELETTE → affiché immédiatement, pipeline continue derrière
                    if node_name == "day_skeleton" and update.get("day_skeleton"):
                        print("\nAssistant (aperçu immédiat) :")
                        print(update["day_skeleton"]["display_text"])
                        print("\n   … je complète votre journée en détail …")
                        skeleton_shown = True

            duration = time.time() - start
            print("\nTraveller ID:", result.get("travellerId"))
    
            # ── Affichage résultats ───────────────────────────────────────
            print("\n──────── RESULT ────────")
            intent_result = result.get("intent_result", {})
            print("Primary Intent :", intent_result.get("primary_intent"))
            print("Secondary Intents:", intent_result.get("secondary_intents"))
            print("Action Type    :", intent_result.get("action_type"))
            print("Confidence     :", intent_result.get("intent_confidence"))
            print("Duration       :", round(duration, 2), "s")

            # Affichage contraintes extraites
            constraints = result.get("intent_result", {}).get("constraints", {})
            print("\nConstraints:")
            print(json.dumps(constraints, indent=2, ensure_ascii=False))


            final_answer = result.get("final_answer") or ""
            if final_answer:
                if skeleton_shown:
                    print("\nAssistant (journée complète) :")
                    print(final_answer)
                else:
                    print("\nAssistant:", final_answer)
                            
            if os.getenv("DEBUG_MODE") == "true":
                print("\n================ DEBUG CONTEXT ================\n")

                debug_fields = [
                    "profile_data",
                    "intent_result",
                    "conversation_context",
                    "weather",
                    "merged_candidates",
                    "ranked_candidates",
                    "day_plan",
                ]

                for field in debug_fields:
                    if field not in result:
                        continue

                    print(f"\n######## {field} ########")

                    try:
                        print(json.dumps(result[field], indent=2, ensure_ascii=False))
                    except TypeError:
                        print(result[field])

                print("\n===============================================\n")
            
            
            
            
            # update state sans écraser
            for key, value in result.items():
                if key in ("errors", "node_metrics", "conversation_history"):
                    continue
                state[key] = value

            # ── last_candidates : mise à jour si ce tour a produit des recommandations ──
            new_candidates = extract_last_candidates(result)
            if new_candidates:
                state["last_candidates"] = new_candidates

            # ── save de history conversation ──
            state.setdefault("conversation_history", [])
            state["conversation_history"].append({
                "role":    "user",
                "content": user_message,
            })
            if final_answer:
                state["conversation_history"].append({
                    "role": "assistant",
                    "content": final_answer,
                })

            # ── Persistance session dans Redis ────────────────────────────────
            dest_now = (result.get("merged_context") or {}).get("destination")
            session_manager.save(user_id, {
                "last_candidates":        state.get("last_candidates") or [],
                "conversation_last_turn": extract_last_turn(result, user_message),
                "destination":            dest_now,
                "last_intent":            (result.get("intent_result") or {}).get("primary_intent"),
                "suggestion_mode":        result.get("suggestion_mode"),
            })
            # weather_context sauvé séparément avec TTL 2h
            wx = result.get("weather_context")
            if wx and dest_now:
                session_manager.save_weather(dest_now, wx)

    except KeyboardInterrupt:
        print("\nAssistant: À bientôt !")


if __name__ == "__main__":
    main()