# Wolf Cerebrum — Préférences, Apprentissages, Do-Not-Repeat

## Préférences Confirmées
- Git push JAMAIS — l'utilisateur gère les push manuellement
- Commit uniquement quand l'utilisateur dit explicitement "commit"
- Dry-run obligatoire avant toute écriture MongoDB en masse
- Attendre "go" explicite entre les phases

## Do-Not-Repeat (bugs déjà commis)
- Ne jamais retourner `{**state, ...}` depuis un node LangGraph — retourner uniquement les clés mises à jour
- Ne jamais hardcoder une constante dans un service → toujours dans settings.py
- Ne jamais créer un node qui dépend d'un LLM pour de la classification déterministe
- Ne pas mélanger deux rules métier dans un seul node (exclusion → constraint_validator, ranking → ranking_node)

## Learnings
- INFORMATIVE_INTENTS séparé de RECOMMENDATION_INTENTS pour le routing LangGraph
- information_node rule-based : zéro LLM pour les questions de suivi (plus rapide, moins de tokens)
- final_response_node.py reçoit tous les paramètres via `.format()` — les paramètres non présents dans le template sont ignorés silencieusement (Python str.format())
- Les frozensets de mots-clés dans information_node doivent être en minuscules (message normalisé via .lower())
- SessionManager : si Redis down → toutes méthodes retournent silencieusement {}/None (dégradation gracieuse)
- LangGraph fan-in bug : nodes convergents doivent être à la même profondeur sinon double exécution
