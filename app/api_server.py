"""
app/api_server.py
═══════════════════════════════════════════════════════════════════════════════
API HTTP minimale — pont entre l'app mobile (Flutter) et
TravellerPreferencesService (MongoDB, cf. app/services/traveller_preferences_service.py).

N'expose PAS le pipeline LangGraph complet (reste CLI-only via app/main.py
pour l'instant) — uniquement ce qui est nécessaire pour connecter le quiz
d'onboarding au backend : écrire les préférences, marquer un skip, lire le
statut.

Lancement (dev) :
    venv1\\Scripts\\python -m uvicorn app.api_server:app --reload --host 0.0.0.0 --port 8000

Depuis un émulateur Android, le backend est joignable via 10.0.2.2:8000
(localhost de la machine hôte) — cf. mobile/lib/services/onboarding_api_service.dart.
"""

import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.services.traveller_preferences_service import TravellerPreferencesService, TRIP_TYPES

logger = logging.getLogger("api_server")

app = FastAPI(title="ZenifyTrip Onboarding API", version="1.0.0")

# CORS ouvert pour le développement (app mobile + éventuels tests web) —
# à restreindre à des origines explicites avant toute mise en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SetPreferencesRequest(BaseModel):
    user_id: str
    trip_type: Optional[str] = None
    travel_purpose: List[str] = Field(default_factory=list)
    culinary_interests: List[str] = Field(default_factory=list)


class SkipRequest(BaseModel):
    user_id: str


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
