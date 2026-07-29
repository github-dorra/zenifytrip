"""
app/api_server.py
═══════════════════════════════════════════════════════════════════════════════
API HTTP — pont entre l'app mobile existante (chat) et le backend ZenifyTrip :
  1. /api/chat                → pipeline LangGraph complet (recommandations)
  2. /api/onboarding/*         → TravellerPreferencesService (MongoDB)

Lancement (dev) :
    venv1\\Scripts\\python -m uvicorn app.api_server:app --reload --host 0.0.0.0 --port 8000

Depuis un émulateur Android, le backend est joignable via 10.0.2.2:8000
(localhost de la machine hôte) — cf. zenifytrip_mobile/lib/services/.
Cf. GUIDE_INTEGRATION.md pour le pas-à-pas complet de connexion au chat existant.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.graph.builder import build_graph
from app.graph.state import build_initial_state
from app.services.traveller_preferences_service import TravellerPreferencesService, TRIP_TYPES

logger = logging.getLogger("api_server")

app = FastAPI(title="ZenifyTrip API", version="1.0.0")

# CORS ouvert pour le développement (app mobile + éventuels tests web) —
# à restreindre à des origines explicites avant toute mise en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Le graphe LangGraph est coûteux à construire (instancie tous les nodes) —
# une seule fois au démarrage du serveur, jamais par requête.
_graph = build_graph()


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    # Le serveur est SANS ÉTAT (stateless) — le client renvoie l'historique
    # reçu au tour précédent, le serveur le complète et le retourne à jour.
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    conversation_id: str
    final_answer: Optional[str] = None
    conversation_history: List[Dict[str, str]]
    day_skeleton: Optional[Dict[str, Any]] = None


class SetPreferencesRequest(BaseModel):
    user_id: str
    trip_type: Optional[str] = None
    travel_purpose: List[str] = Field(default_factory=list)
    culinary_interests: List[str] = Field(default_factory=list)


class SkipRequest(BaseModel):
    user_id: str


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    """
    Point d'entrée unique du chat existant vers le pipeline de recommandation.
    Exécute le graphe complet (intent → recommandation → réponse naturelle)
    pour UN message, exactement comme app/main.py le fait en CLI.
    """
    session_id = body.session_id or str(uuid.uuid4())
    conversation_id = body.conversation_id or str(uuid.uuid4())

    state = build_initial_state(
        user_message=body.message,
        user_id=body.user_id,
        session_id=session_id,
        conversation_id=conversation_id,
    )
    state["conversation_history"] = body.conversation_history

    result = dict(state)
    for chunk in _graph.stream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            if not isinstance(update, dict):
                continue
            for key, value in update.items():
                if key in ("errors", "node_metrics"):
                    result[key] = (result.get(key) or []) + (value or [])
                else:
                    result[key] = value

    new_history = list(body.conversation_history)
    new_history.append({"role": "user", "content": body.message})
    if result.get("final_answer"):
        new_history.append({"role": "assistant", "content": result["final_answer"]})

    return ChatResponse(
        session_id=session_id,
        conversation_id=conversation_id,
        final_answer=result.get("final_answer"),
        conversation_history=new_history,
        day_skeleton=result.get("day_skeleton"),
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/onboarding/status/{user_id}")
def onboarding_status(user_id: str):
    """
    Appelé au lancement de l'app — indique si le quiz doit être affiché.
    completed=True que le quiz ait été rempli OU explicitement skippé (dans
    les deux cas, ne plus le proposer automatiquement).
    """
    completed = TravellerPreferencesService.has_completed_onboarding(user_id)
    preferences = TravellerPreferencesService.get_preferences(user_id) if completed else None
    return {"has_completed_onboarding": completed, "preferences": preferences}


@app.post("/api/onboarding/preferences")
def set_preferences(body: SetPreferencesRequest):
    if body.trip_type and body.trip_type not in TRIP_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"trip_type invalide — attendu parmi {sorted(TRIP_TYPES)}",
        )

    ok = TravellerPreferencesService.set_preferences(
        user_id=body.user_id,
        trip_type=body.trip_type,
        travel_purpose=body.travel_purpose,
        culinary_interests=body.culinary_interests,
    )
    if not ok:
        raise HTTPException(status_code=503, detail="MongoDB indisponible — réessayez plus tard")
    return {"status": "ok"}


@app.post("/api/onboarding/skip")
def skip_onboarding(body: SkipRequest):
    ok = TravellerPreferencesService.mark_skipped(body.user_id)
    if not ok:
        raise HTTPException(status_code=503, detail="MongoDB indisponible — réessayez plus tard")
    return {"status": "ok"}
