"""
Mémoire de session MVP — mining rule-based de conversation_history.
Intra-session uniquement (la v2 Redis cross-session = Phase 5).

RÈGLE DE SÉCURITÉ — fenêtre de proximité :
le marqueur et le mot-clé doivent être à MOINS de 5 mots l'un de l'autre
(distance d'index < 5, mot-clé APRÈS le marqueur).
  "pas de plage"                  → distance 2 → rejet ✓
  "pas de problème avec la plage" → distance 5 → PAS de rejet ✓
"""
import re
from typing import Any, Dict, List

from app.utils.text_utils import normalize_text

# Tokenisation : mots alphanumériques uniquement — la ponctuation collée
# ("quad," / "plage!") ne doit jamais casser le matching
_WORD_RE = re.compile(r"[a-z0-9]+")

REJECTION_WINDOW = 5   # distance d'index max EXCLUSIVE (< 5 mots)

# Marqueurs de rejet (mots normalisés)
_REJECT_MARKERS = {"pas", "sans", "non", "jamais", "evite", "eviter", "no", "not", "avoid", "skip"}

# Marqueurs positifs
_LIKE_MARKERS = {"adore", "aime", "prefere", "parfait", "super", "genial", "love", "like", "prefer"}

# Neutralisateurs — si présents entre marqueur et mot-clé → pas un rejet
# ("pas mal la plage", "pas de souci pour le musée")
_NEUTRALIZERS = {"mal", "probleme", "souci", "soucis"}

# Mots-clés utilisateur (normalisés) → activity_type des candidats
_KEYWORD_TO_TYPE = {
    "plage": "nature", "plages": "nature", "beach": "nature", "mer": "nature",
    "nature": "nature", "randonnee": "nature", "parc": "nature",
    "musee": "culture", "musees": "culture", "museum": "culture", "museums": "culture",
    "medina": "culture", "culture": "culture", "culturel": "culture", "culturelle": "culture",
    "histoire": "culture", "historique": "culture", "monument": "culture", "mosquee": "culture",
    "quad": "adventure", "plongee": "adventure", "aventure": "adventure", "adventure": "adventure",
    "surf": "adventure", "jetski": "adventure", "sport": "adventure", "sports": "adventure",
    "spa": "relax", "hammam": "relax", "massage": "relax", "detente": "relax",
    "relax": "relax", "repos": "relax",
    "souk": "city_experience", "souks": "city_experience", "marche": "city_experience",
    "shopping": "city_experience", "boutiques": "city_experience",
}

_MAX_TURNS = 10   # ne mine que les 10 derniers tours user


def extract_session_signals(conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Retourne {"rejected_types": [...], "liked_types": [...]} depuis les tours user.
    Déterministe, aucun LLM. Le rejet PRIME sur le like pour un même mot-clé.
    """
    rejected: set = set()
    liked: set = set()

    user_turns = [t.get("content", "") for t in (conversation_history or [])
                  if t.get("role") == "user"][-_MAX_TURNS:]

    for turn in user_turns:
        words = _WORD_RE.findall(normalize_text(turn))
        for j, word in enumerate(words):
            activity_type = _KEYWORD_TO_TYPE.get(word)
            if not activity_type:
                continue

            # Rejet : marqueur AVANT le mot-clé, distance < REJECTION_WINDOW,
            # sans neutralisateur entre les deux
            is_rejected = False
            for i in range(max(0, j - REJECTION_WINDOW + 1), j):
                if words[i] in _REJECT_MARKERS:
                    between = set(words[i + 1:j])
                    if not (between & _NEUTRALIZERS):
                        is_rejected = True
                        break

            if is_rejected:
                rejected.add(activity_type)
                continue          # le rejet prime — pas de like sur ce mot-clé

            # Like : même fenêtre
            for i in range(max(0, j - REJECTION_WINDOW + 1), j):
                if words[i] in _LIKE_MARKERS:
                    liked.add(activity_type)
                    break

    liked -= rejected             # cohérence : jamais liked ET rejected
    return {"rejected_types": sorted(rejected), "liked_types": sorted(liked)}
