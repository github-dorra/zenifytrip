"""
ZenifyTrip — FastAPI web server wrapping the LangGraph pipeline.
Endpoint principal : POST /chat
"""
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.graph.builder import build_graph
from app.graph.state import build_initial_state
from app.services.session_manager import SessionManager, _trim_candidates
from app.config.settings import SESSION_MAX_CANDIDATES, SESSION_MAX_TURN_CHARS

# ── Initialisation ────────────────────────────────────────────────────────────

app = FastAPI(
    title="ZenifyTrip Assistant API",
    description="Système de recommandation touristique multi-agents LangGraph",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = build_graph()
session_manager = SessionManager()


# ── Schémas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str
    user_message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    final_answer: str
    primary_intent: Optional[str] = None
    suggestion_mode: Optional[str] = None
    duration_seconds: float
    session_id: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "zenifytrip-assistant", "version": "1.0.0"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())

    # Chargement de la session persistée (Redis — fallback {} si Redis down)
    session = session_manager.load(req.user_id)

    # Construction de l'état initial
    state = build_initial_state(
        user_message=req.user_message,
        user_id=req.user_id,
        session_id=session_id,
        conversation_id=str(uuid.uuid4()),
        travellerId="",
    )

    # Injection du contexte cross-tour depuis la session
    if session.get("last_candidates"):
        state["last_candidates"] = session["last_candidates"]
    if session.get("conversation_history"):
        state["conversation_history"] = session["conversation_history"]

    # Météo mise en cache séparément (TTL 2h)
    dest_hint = session.get("destination") or (state.get("merged_context") or {}).get("destination")
    if dest_hint:
        cached_wx = session_manager.load_weather(dest_hint)
        if cached_wx:
            state["weather_context"] = cached_wx

    # ── Exécution du graphe ──────────────────────────────────────────────────
    start = time.time()
    result = dict(state)

    for chunk in graph.stream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            if not isinstance(update, dict):
                continue
            for key, value in update.items():
                if key in ("errors", "node_metrics"):
                    result[key] = (result.get(key) or []) + (value or [])
                else:
                    result[key] = value

    duration = time.time() - start
    final_answer = result.get("final_answer") or ""

    # ── Mise à jour conversation_history ────────────────────────────────────
    conv_history = list(session.get("conversation_history") or [])
    conv_history.append({"role": "user", "content": req.user_message})
    if final_answer:
        conv_history.append({"role": "assistant", "content": final_answer})
    conv_history = conv_history[-20:]  # 10 tours max en mémoire

    # ── Extraction des candidats présentés ──────────────────────────────────
    ranked = result.get("ranked_results") or []
    new_candidates = _trim_candidates(ranked[:SESSION_MAX_CANDIDATES]) if ranked else []

    # ── Persistance session ──────────────────────────────────────────────────
    dest_now = (result.get("merged_context") or {}).get("destination")
    session_manager.save(req.user_id, {
        "last_candidates":        new_candidates or session.get("last_candidates") or [],
        "conversation_last_turn": [
            {"role": "user",      "content": req.user_message[:SESSION_MAX_TURN_CHARS]},
            {"role": "assistant", "content": final_answer[:SESSION_MAX_TURN_CHARS]},
        ],
        "conversation_history": conv_history,
        "destination":   dest_now or session.get("destination"),
        "last_intent":   (result.get("intent_result") or {}).get("primary_intent"),
        "suggestion_mode": result.get("suggestion_mode"),
    })

    wx = result.get("weather_context")
    if wx and dest_now:
        session_manager.save_weather(dest_now, wx)

    return ChatResponse(
        final_answer=final_answer,
        primary_intent=(result.get("intent_result") or {}).get("primary_intent"),
        suggestion_mode=result.get("suggestion_mode"),
        duration_seconds=round(duration, 2),
        session_id=session_id,
    )
