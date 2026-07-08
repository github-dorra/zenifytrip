from app.graph.builder import build_graph
from app.graph.state import build_initial_state
import json 
import time
import uuid

def main():
    graph = build_graph()

    state = build_initial_state(
        user_message   = "",
        user_id= "df55d964-039d-4838-8e5e-352ce1708bd9",   #"2720b441-6e48-464f-880b-71dd2d4cdca5",
        session_id= str(uuid.uuid4()),
        conversation_id= str(uuid.uuid4()),
        travellerId="",
    )

    print("Assistant: Bonjour ! Où souhaitez-vous partir ?")

    try:
        while True:
            user_message = input("\nUser: ").strip()
            if not user_message:
                print("Assistant: Please enter a message.")
                continue

            state["user_message"] = user_message

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
                
            
            # save de history conversation 
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

    except KeyboardInterrupt:
        print("\nAssistant: À bientôt !")


if __name__ == "__main__":
    main()