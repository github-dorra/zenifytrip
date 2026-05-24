from app.graph.builder import build_graph
import json 
import time
import uuid

def main():
    graph = build_graph()

    state = {
        "user_id": "2720b441-6e48-464f-880b-71dd2d4cdca5",
        "session_id": str(uuid.uuid4()),
        "travellerId":"",
        "locale": "fr",
        "user_message": "",
        "conversation_history": [],
        "errors": [],
        "final_answer": "",
    }

    print("Assistant: Bonjour ! Où souhaitez-vous partir ?")

    try:
        while True:
            user_message = input("\nUser: ")

            state["user_message"] = user_message

            start = time.time()
            result = graph.invoke(state)
            print("\nTraveller ID:", result.get("travellerId"))
            duration = time.time() - start
    

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
            
            # save de history conversation 
            state.setdefault("conversation_history", [])

            state["conversation_history"].append({
                "role": "user",
                "content": user_message
            })

            state["conversation_history"].append({
                "role": "assistant",
                "content": result.get("final_answer", "")
            })

            # Réponse finale
            if result.get("final_answer"):
                print("\nAssistant:", result["final_answer"])

            # update state proprement
            state.update(result)

    except KeyboardInterrupt:
        print("\nAssistant: À bientôt !")


if __name__ == "__main__":
    main()