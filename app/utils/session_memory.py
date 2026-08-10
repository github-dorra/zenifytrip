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
    "shopping": "city_experience", "boutiques": "city_experience", "boutique": "city_experience",
    # Souvenir / artisanat / commerce — absents avant, ajoutés fix 2026-08-10
    "souvenir": "city_experience", "souvenirs": "city_experience",
    "artisanat": "city_experience", "artisan": "city_experience", "artisans": "city_experience",
    "mall": "city_experience", "bazar": "city_experience", "bazaar": "city_experience",
    "freeshop": "city_experience", "hanout": "city_experience",
}

# Mots-clés signalant un rejet d'excursion / visite privée (détection distincte de activity_type)
# Utilisés pour reject_private_tour uniquement — fenêtre plus large (7 mots)
_PRIVATE_TOUR_WORDS = frozenset({
    "excursion", "excursions", "prive", "privee", "privees", "prives",
    "guidee", "guidees", "guide", "guides", "vip",
})
# Marqueurs de rejet étendus (inclut "autre" pour "autre chose que les excursions")
_EXTENDED_REJECT_MARKERS = frozenset({
    "pas", "sans", "non", "jamais", "evite", "eviter", "no", "not", "avoid", "skip",
    "autre", "plutot", "different", "instead", "plus",
})

_MAX_TURNS = 10   # ne mine que les 10 derniers tours user


def extract_session_signals(conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Retourne {"rejected_types": [...], "liked_types": [...], "reject_private_tour": bool}.
    Déterministe, aucun LLM. Le rejet PRIME sur le like pour un même mot-clé.

    reject_private_tour=True quand le user rejette les excursions/visites guidées/privées
    (ex : "pas d'excursion", "autre chose que les excursions", "sans visite guidée").
    Utilise une fenêtre étendue de 7 mots + marqueurs élargis ("autre", "plutot", "plus").
    """
    rejected: set = set()
    liked: set = set()
    reject_private_tour = False

    _PRIVATE_TOUR_WINDOW = 7   # fenêtre plus large que REJECTION_WINDOW

    user_turns = [t.get("content", "") for t in (conversation_history or [])
                  if t.get("role") == "user"][-_MAX_TURNS:]

    for turn in user_turns:
        words = _WORD_RE.findall(normalize_text(turn))
        for j, word in enumerate(words):
            # ── Détection reject_private_tour (fenêtre 7, marqueurs étendus) ──
            if not reject_private_tour and word in _PRIVATE_TOUR_WORDS:
                for i in range(max(0, j - _PRIVATE_TOUR_WINDOW + 1), j):
                    if words[i] in _EXTENDED_REJECT_MARKERS:
                        between = set(words[i + 1:j])
                        if not (between & _NEUTRALIZERS):
                            reject_private_tour = True
                            break

            # ── Détection activity_type rejected / liked ──
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
    return {
        "rejected_types": sorted(rejected),
        "liked_types": sorted(liked),
        "reject_private_tour": reject_private_tour,
    }
