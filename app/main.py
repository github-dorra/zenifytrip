from app.graph.builder import build_graph
from app.graph.state import build_initial_state
import json 
import time
import uuid

def main():
    graph = build_graph()

    state = build_initial_state(
        user_message   = "",
        user_id= "2720b441-6e48-464f-880b-71dd2d4cdca5",
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

            # ── Invocation du graphe ──────────────────────────────────────
            start = time.time()
            result = graph.invoke(state)
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
                print("\nAssistant:", final_answer)
            
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