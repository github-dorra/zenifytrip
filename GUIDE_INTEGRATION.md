# Guide d'intégration — ZenifyTrip

> Guide pas-à-pas, écrit pour quelqu'un qui découvre le projet. Chaque étape a été
> testée réellement (vraies requêtes HTTP, vraie base MongoDB) avant d'être écrite ici —
> pas de supposition, tout ce qui est décrit fonctionne tel quel.

## Vue d'ensemble — les 3 pièces du puzzle

```
┌─────────────────────────┐        ┌──────────────────────────┐        ┌─────────────────┐
│   APP MOBILE EXISTANTE   │        │   app/api_server.py      │        │   MongoDB Atlas   │
│   (le chat qui existe    │  HTTP  │   (FastAPI, "le pont")    │        │                   │
│    déjà)                 │◄──────►│                           │◄──────►│  traveller_       │
│                          │        │  /api/chat                │        │  preferences      │
│  + Écran quiz onboarding │        │  /api/onboarding/status    │        │  traveller_       │
│    (zenifytrip_mobile)   │        │  /api/onboarding/preferences│       │  profile_cache    │
└─────────────────────────┘        │  /api/onboarding/skip     │        └─────────────────┘
                                     │        │                          
                                     │        ▼                          
                                     │  app/graph/builder.py     
                                     │  (le pipeline LangGraph — 
                                     │   toute l'intelligence)   
                                     └──────────────────────────┘
```

**Le principe clé à comprendre** : le pipeline de recommandation (LangGraph, tout ce qui est décrit dans `CLAUDE.md`) ne parlait jusqu'ici qu'en ligne de commande (`python -m app.main`). `app/api_server.py` est la seule porte d'entrée HTTP vers ce pipeline — c'est LA pièce qui permet à n'importe quelle app (mobile, web) de lui parler. Tout ce guide tourne autour de cette porte d'entrée.

---

## Étape 1 — Lancer le backend

C'est le préalable à tout le reste. Rien ne fonctionnera si cette étape n'est pas faite.

```bash
cd zenifyTrip-tourism-system
venv1\Scripts\python -m uvicorn app.api_server:app --reload --host 0.0.0.0 --port 8000
```

Vérifier que ça tourne (dans un autre terminal, ou un navigateur) :
```
http://127.0.0.1:8000/api/health
→ {"status": "ok"}
```

Si cette réponse n'apparaît pas, rien d'autre ne peut fonctionner — s'arrêter ici et vérifier les logs affichés dans le terminal (souvent : `.env` manquant, `MONGODB_URI` absente, ou `GROQ_API_KEY`/`GEMINI_API_KEY` manquante).

**Adresse à utiliser depuis le téléphone/émulateur, selon la cible :**

| Cible | Adresse à utiliser dans le code Flutter |
|---|---|
| Émulateur Android | `http://10.0.2.2:8000` (déjà utilisé dans le projet Flutter) |
| Simulateur iOS | `http://127.0.0.1:8000` |
| Chrome (`flutter run -d chrome`) | `http://127.0.0.1:8000` |
| Téléphone physique | `http://<IP locale de l'ordinateur>:8000` (les deux appareils doivent être sur le même Wi-Fi) |

---

## Étape 2 — Intégrer le système de recommandation dans le chat existant

C'est le cœur du sujet : brancher le chat déjà présent dans l'app sur le pipeline ZenifyTrip.

### 2.1 — Un seul endpoint à connaître : `POST /api/chat`

**Ce qu'on envoie :**
```json
{
  "user_id": "identifiant-du-voyageur",
  "message": "je veux un restaurant à Sousse",
  "session_id": null,
  "conversation_id": null,
  "conversation_history": []
}
```

**Ce qu'on reçoit :**
```json
{
  "session_id": "généré automatiquement si absent en entrée",
  "conversation_id": "généré automatiquement si absent en entrée",
  "final_answer": "Pour manger à Sousse, je te conseille le Café et Restaurant Kasbah...",
  "conversation_history": [
    {"role": "user", "content": "je veux un restaurant à Sousse"},
    {"role": "assistant", "content": "Pour manger à Sousse, je te conseille..."}
  ],
  "day_skeleton": null
}
```

### 2.2 — Règle à retenir : le serveur ne se souvient de RIEN entre deux messages

C'est le point le plus important à comprendre pour un débutant : `api_server.py` est **sans état** (« stateless »). Il ne garde pas en mémoire ce qui a été dit avant. C'est le chat de l'app (le client) qui doit :
1. Garder `conversation_history` reçu dans la réponse précédente
2. Le renvoyer tel quel dans le message suivant
3. Faire pareil avec `session_id` et `conversation_id`

Sans ça, chaque message serait traité comme si c'était le tout premier message de la conversation — le système oublierait tout ce qui a été dit avant (la destination déjà mentionnée, etc.).

### 2.3 — Où brancher ça concrètement dans le chat existant

Peu importe la techno du chat existant (Flutter, React Native, natif...), le principe est toujours le même 3 étapes :

1. **Quand l'utilisateur envoie un message** dans le chat → appeler `POST /api/chat` avec ce message + l'historique gardé en mémoire locale de l'écran de chat.
2. **Afficher `final_answer`** dans la bulle de réponse de l'assistant (c'est déjà écrit en langage naturel, prêt à afficher tel quel — inutile de le retraiter).
3. **Remplacer** l'historique local par le `conversation_history` reçu dans la réponse (il contient déjà l'ancien + le nouveau message).

Exemple concret en Dart (le langage du chat existant, si c'est du Flutter) :

```dart
class ChatService {
  static const String baseUrl = 'http://10.0.2.2:8000'; // adapter selon la cible (tableau ci-dessus)

  static Future<Map<String, dynamic>> sendMessage({
    required String userId,
    required String message,
    String? sessionId,
    String? conversationId,
    List<Map<String, String>> history = const [],
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/api/chat'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'user_id': userId,
        'message': message,
        'session_id': sessionId,
        'conversation_id': conversationId,
        'conversation_history': history,
      }),
    );
    return jsonDecode(res.body) as Map<String, dynamic>;
  }
}
```

Puis dans l'écran de chat, à chaque envoi de message :
```dart
final response = await ChatService.sendMessage(
  userId: monUserId,
  message: texteTapeParUtilisateur,
  sessionId: monSessionIdActuel,        // null au tout premier message
  conversationId: monConversationIdActuel,
  history: monHistoriqueLocal,
);

// Afficher response['final_answer'] dans la bulle de l'assistant
// Puis mettre à jour l'état local :
monSessionIdActuel = response['session_id'];
monConversationIdActuel = response['conversation_id'];
monHistoriqueLocal = response['conversation_history'];
```

C'est tout — il n'y a rien d'autre à comprendre du pipeline LangGraph pour l'intégrer. Toute la complexité (classification d'intention, recommandations, ranking...) est cachée derrière cet unique endpoint.

---

## Étape 3 — Intégrer le quiz d'onboarding dans l'app

Le quiz existe déjà, entièrement codé, dans le dossier `zenifytrip_mobile/` (projet Flutter séparé). Cette étape explique comment le brancher dans l'app existante — pas comment le recoder.

### 3.1 — Le déclenchement : au tout premier lancement de l'app

La logique est déjà écrite dans `zenifytrip_mobile/lib/main.dart` — voici le principe à reproduire dans l'app existante si le quiz doit y être intégré directement (plutôt que dans le projet Flutter séparé) :

1. Au démarrage de l'app, appeler `GET /api/onboarding/status/{user_id}`
2. Si `has_completed_onboarding` vaut `false` → afficher l'écran de quiz
3. Si `true` → aller directement à l'écran principal (le quiz a déjà été rempli **ou** explicitement passé — dans les deux cas, ne plus le proposer)

```dart
final status = await http.get(Uri.parse('$baseUrl/api/onboarding/status/$userId'));
final data = jsonDecode(status.body);
if (data['has_completed_onboarding'] == false) {
  // afficher l'écran de quiz (OnboardingQuizScreen)
} else {
  // aller directement à l'app
}
```

**Important — ne jamais bloquer l'app si le serveur ne répond pas** : si l'appel échoue (pas de réseau, backend éteint), il faut quand même laisser entrer l'utilisateur dans l'app (sauter le quiz cette fois-ci) plutôt que de le bloquer sur un écran de chargement infini. C'est déjà géré ainsi dans `main.dart` du projet Flutter fourni.

### 3.2 — Copier les écrans du quiz dans l'app existante

Si le chat existant est aussi en Flutter, la façon la plus simple d'intégrer le quiz est de copier ces fichiers du projet `zenifytrip_mobile/` vers l'app existante :

```
lib/theme/app_theme.dart                              → design (couleurs, polices)
lib/models/quiz_question.dart                         → modèle de données
lib/data/onboarding_quiz_data.dart                     → les 3 questions
lib/services/onboarding_api_service.dart               → appels réseau
lib/services/user_id_service.dart                      → identifiant local
lib/screens/onboarding/onboarding_quiz_screen.dart      → écran principal
lib/screens/onboarding/onboarding_summary_screen.dart   → écran récap
lib/screens/onboarding/widgets/                        → les 2 petits composants visuels
```

Puis, dans l'app existante, insérer la logique de l'étape 3.1 avant d'afficher l'écran principal habituel — exactement comme `main.dart` le fait dans le projet fourni.

Si le chat existant N'est PAS en Flutter (React Native, Swift/Kotlin natif...), les fichiers Dart ne sont pas réutilisables directement, mais **le design (couleurs, structure d'écran) et les 3 appels API (`status`/`preferences`/`skip`) restent identiques** — seule la traduction dans le langage de l'app change.

---

## Étape 4 — Vérifier que les réponses du quiz sont bien sauvegardées dans MongoDB

Ceci se passe déjà automatiquement une fois l'écran de quiz connecté (étape 3) — mais voici comment **vérifier concrètement** que ça fonctionne, utile pour un débutant qui veut être sûr avant de continuer.

### 4.1 — Ce qui se passe en coulisses quand l'utilisateur termine le quiz

1. L'écran de quiz appelle `POST /api/onboarding/preferences` avec les réponses choisies
2. `api_server.py` transmet ça à `TravellerPreferencesService.set_preferences()`
3. Ce service écrit un document dans MongoDB Atlas, collection **`traveller_preferences`**
4. Chaque fois que ce même `user_id` envoie un message de chat ensuite, le pipeline relit automatiquement ces préférences (via `profile_loader_node` → `context_merger_node`) et les utilise pour personnaliser les recommandations — **sans rien reconfigurer côté app**.

### 4.2 — Vérifier directement dans MongoDB (ligne de commande)

```bash
cd zenifyTrip-tourism-system
venv1\Scripts\python -c "
from dotenv import load_dotenv
load_dotenv()
from app.config.mongodb import traveller_preferences_collection
# Remplacer USER_ID par l'identifiant utilisé lors du test du quiz
doc = traveller_preferences_collection().find_one({'_id': 'USER_ID'})
print(doc)
"
```

Si le quiz a été rempli correctement, ça doit afficher quelque chose comme :
```python
{'_id': 'USER_ID', 'trip_type': 'couple', 'travel_purpose': ['gastronomie'],
 'culinary_interests': ['fruits_de_mer'], 'completed_at': ..., 'skipped': False, 'updated_at': ...}
```

### 4.3 — Vérifier que ça influence vraiment les recommandations

Test simple, sans même toucher à l'app :
1. Remplir le quiz pour un `user_id` de test (via l'app, ou directement via `POST /api/onboarding/preferences`)
2. Appeler `POST /api/chat` avec ce même `user_id` et un message du type `"je veux un restaurant à Djerba"` **sans mentionner de cuisine particulière**
3. Si les préférences ont bien été prises en compte, les restaurants recommandés doivent correspondre au goût indiqué dans le quiz (ex. fruits de mer) — pas des restaurants au hasard.

Ce comportement a été vérifié réellement pendant le développement — voir la section « VERSION 7 » de `CLAUDE.md` pour le détail du test (avant/après, candidats concrets).

---

## Checklist récapitulative

- [ ] `uvicorn app.api_server:app` tourne et répond sur `/api/health`
- [ ] L'app (chat) appelle `POST /api/chat` à chaque message, en renvoyant `session_id`/`conversation_id`/`conversation_history` reçus au tour précédent
- [ ] `final_answer` s'affiche tel quel dans la bulle de réponse de l'assistant
- [ ] Au premier lancement, l'app appelle `GET /api/onboarding/status/{user_id}` avant d'afficher l'écran principal
- [ ] Si `has_completed_onboarding=false`, l'écran de quiz s'affiche (bouton "Passer" toujours visible)
- [ ] Une fois le quiz terminé/passé, `POST /api/onboarding/preferences` ou `/skip` a bien été appelé
- [ ] Vérification MongoDB : le document apparaît dans `traveller_preferences`
- [ ] Un nouveau message de chat pour ce même utilisateur reflète bien ses préférences dans les recommandations
