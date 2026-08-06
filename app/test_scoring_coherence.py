"""
test_scoring_coherence.py — Tests de cohérence des 3 améliorations Scoring V2

Vérifie :
  ① proximity_score : flux distance_km → _to_candidate() → score() → RestaurantCandidate
  ② hours_score     : flux opening_hours_text → score(request_hour=) → matched_criteria
  ③ weather_factor  : flux weather_context → ranking_node._weather_factor()
  + outdoor_score formula (weather_service.py) fix sun_ratio
  + Bugs silencieux potentiels détectés lors de l'analyse

Exécution : python -m app.test_scoring_coherence
"""

import sys

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    msg = f"  {status}  {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    results.append((name, condition))
    return condition


# ═══════════════════════════════════════════════════════════════════════
# SECTION A — _proximity_score()
# ═══════════════════════════════════════════════════════════════════════

print("\n─── A. _proximity_score() ───────────────────────────────────────")

from app.services.mongo_restaurant_service import MongoRestaurantService
from app.config.settings import RESTAURANT_PROXIMITY_MAX_KM

ps = MongoRestaurantService._proximity_score

check("None → 0.5 (neutre)",          ps(None) == 0.5,
      f"got {ps(None)}")

check("0 km → 1.0",                   ps(0.0) == 1.0,
      f"got {ps(0.0)}")

check("max km → plancher 0.1",         ps(RESTAURANT_PROXIMITY_MAX_KM) == 0.1,
      f"got {ps(RESTAURANT_PROXIMITY_MAX_KM)} (max={RESTAURANT_PROXIMITY_MAX_KM}km)")

check("mi-chemin (2.5km / 5km max) → 0.5",
      ps(RESTAURANT_PROXIMITY_MAX_KM / 2) == 0.5,
      f"got {ps(RESTAURANT_PROXIMITY_MAX_KM / 2)}")

check("au-delà du max → plancher 0.1", ps(RESTAURANT_PROXIMITY_MAX_KM * 2) == 0.1,
      f"got {ps(RESTAURANT_PROXIMITY_MAX_KM * 2)}")

check("décroissance monotone (0→max)",
      ps(0.0) > ps(1.0) > ps(2.5) > ps(RESTAURANT_PROXIMITY_MAX_KM),
      f"1.0 > {ps(1.0)} > {ps(2.5)} > {ps(RESTAURANT_PROXIMITY_MAX_KM)}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION B — _hours_score()
# ═══════════════════════════════════════════════════════════════════════

print("\n─── B. _hours_score() ───────────────────────────────────────────")

hs = MongoRestaurantService._hours_score

# Ouvert maintenant (h=12 dans 10:00-22:00)
check("ouvert midi → 1.0",             hs("10:00-22:00", 12) == 1.0, f"got {hs('10:00-22:00', 12)}")
check("ouvert le soir → 1.0",          hs("19h-23h30", 20)  == 1.0, f"got {hs('19h-23h30', 20)}")

# Fermé maintenant
check("fermé matin → 0.3",             hs("12:00-23:00", 9)  == 0.3, f"got {hs('12:00-23:00', 9)}")
check("fermé le soir tard → 0.3",      hs("10:00-22:00", 23) == 0.3, f"got {hs('10:00-22:00', 23)}")

# Format heure française
check("format fr '11h30-14h30' → 1.0", hs("11h30-14h30", 12) == 1.0, f"got {hs('11h30-14h30', 12)}")
check("format fr hors plage → 0.3",    hs("11h30-14h30", 16) == 0.3, f"got {hs('11h30-14h30', 16)}")

# Chevauchement minuit
check("24h ouvert → 1.0",              hs("Ouvert 24h/24", 3) == 1.0, f"got {hs('Ouvert 24h/24', 3)}")
check("minuit overlap 20h-02h (h=23)", hs("20:00-02:00", 23) == 1.0, f"got {hs('20:00-02:00', 23)}")
check("minuit overlap 20h-02h (h=1)",  hs("20:00-02:00", 1)  == 1.0, f"got {hs('20:00-02:00', 1)}")
check("minuit overlap 20h-02h (h=3) → 0.3", hs("20:00-02:00", 3) == 0.3, f"got {hs('20:00-02:00', 3)}")

# Cas neutres
check("None hours → 0.5",             hs(None, 12) == 0.5,   f"got {hs(None, 12)}")
check("no request_hour → 0.5",        hs("10:00-22:00", None) == 0.5, f"got {hs('10:00-22:00', None)}")
check("format non reconnu → 0.5",     hs("voir sur place", 14) == 0.5, f"got {hs('voir sur place', 14)}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION C — _to_candidate() : flux de champs vers score()
# ═══════════════════════════════════════════════════════════════════════

print("\n─── C. _to_candidate() flux de champs ──────────────────────────")

# Doc MongoDB typique avec GPS et horaires
doc = {
    "_id": "abc123",
    "name": "Dar Bibi",
    "city": "monastir",
    "zone": "Gouvernorat de Monastir",
    "geo": {"lat": 35.77, "lng": 10.82},
    "rating": 4.6,
    "reviews": 215,
    "price_level": "€€",
    "categories": ["Tunisien", "Méditerranéen"],
    "tags": ["terrasse", "vue mer"],
    "features": ["terrasse"],
    "opening_hours_text": "12:00-23:00",
    "establishment_types": ["restaurant"],
    "source": "restaurantguru",
    "photo_url": "https://example.com/photo.jpg",
}

# Avec GPS de référence (mode nearby)
ref_lat, ref_lng = 35.75, 10.80  # ~2.7 km de l'hôtel
c = MongoRestaurantService._to_candidate(doc, ref_lat=ref_lat, ref_lng=ref_lng)

check("distance_km calculée (GPS ref present)", c["distance_km"] is not None and c["distance_km"] > 0,
      f"got {c['distance_km']}")

check("opening_hours_text dans le dict brut",  "opening_hours_text" in c,
      "champ présent avant Pydantic validation")

check("_city private field dans le dict brut", "_city" in c and c["_city"] == "monastir",
      f"got {c.get('_city')}")

# Score via score() AVANT Pydantic (comme dans MongoRestaurantService.search())
sc_with_gps, crit_with_gps = MongoRestaurantService.score(
    c, ["cuisine tunisienne"], "medium",
    is_family=False, search_relevance_norm=0.8,
    destination="monastir", request_hour=14
)

check("score() avec GPS+horaires > 0",         sc_with_gps > 0.0,
      f"got user_score={sc_with_gps}")

check("'possibly_closed' absent à 14h (ouvert 12-23)", "possibly_closed" not in crit_with_gps,
      f"criteria={crit_with_gps}")

# Même document, heure fermée (h=9)
sc_closed, crit_closed = MongoRestaurantService.score(
    c, ["cuisine tunisienne"], "medium",
    is_family=False, search_relevance_norm=0.8,
    destination="monastir", request_hour=9
)

check("'possibly_closed' présent à 9h (fermé)", "possibly_closed" in crit_closed,
      f"criteria={crit_closed}")

check("score fermé < score ouvert (malus 0.3 vs 1.0)", sc_closed < sc_with_gps,
      f"closed={sc_closed} < open={sc_with_gps}")

# Sans GPS de référence (mode destination/exploratoire)
c_no_gps = MongoRestaurantService._to_candidate(doc, ref_lat=None, ref_lng=None)
check("distance_km None sans GPS ref",         c_no_gps["distance_km"] is None,
      f"got {c_no_gps['distance_km']}")

sc_no_gps, _ = MongoRestaurantService.score(
    c_no_gps, [], None, is_family=False,
    search_relevance_norm=0.5, destination="monastir", request_hour=None
)
# Sans GPS et sans horaire → proximity=0.5 (neutre), hours=0.5 (neutre)
check("score sans GPS/horaire ≈ neutre (0.4–0.7)", 0.4 <= sc_no_gps <= 0.7,
      f"got {sc_no_gps}")

# ── Pydantic validation : distance_km preserved, opening_hours_text dropped ──
from app.schemas.restaurant_schema import RestaurantCandidate

# Simuler le dict complet tel que retourné par search()
c_full = dict(c)
c_full["user_score"]     = sc_with_gps
c_full["matched_criteria"] = crit_with_gps
c_full["business_score"] = 0.6

try:
    validated = RestaurantCandidate(**c_full).model_dump()
    check("RestaurantCandidate validate OK",   True)
    check("distance_km préservé après Pydantic", validated.get("distance_km") is not None,
          f"got {validated.get('distance_km')}")
    check("user_score préservé après Pydantic",  validated.get("user_score") == sc_with_gps,
          f"got {validated.get('user_score')}")
    # opening_hours_text absent de RestaurantCandidate → logiquement absent
    # mais le scoring a déjà été fait sur le dict brut → pas de bug fonctionnel
    opening_absent = "opening_hours_text" not in validated
    check("opening_hours_text absent après Pydantic (scoring déjà fait)",
          opening_absent,
          "normal — score calculé sur dict brut avant validation")
    _city_absent = "_city" not in validated
    check("_city absent après Pydantic (champ interne)", _city_absent,
          "normal — champ interne non exposé")
except Exception as e:
    check("RestaurantCandidate validate OK", False, str(e))


# ═══════════════════════════════════════════════════════════════════════
# SECTION D — _weather_factor() cohérence avec le state LangGraph
# ═══════════════════════════════════════════════════════════════════════

print("\n─── D. _weather_factor() cohérence ─────────────────────────────")

from app.nodes.recommendation.postprocessing.ranking_node import RankingNode
from app.config.settings import WEATHER_FACTOR_MIN

wf = RankingNode._weather_factor

# ── D1 : weather_context tel que stocké par weather_node (model_dump) ──
# Beau temps : outdoor_score=1.0 (après fix), indoor_score=0.4
good_weather = {
    "available": True,
    "insights": {
        "outdoor_score": 1.0,
        "indoor_score":  0.4,
    }
}

bad_weather = {
    "available": True,
    "insights": {
        "outdoor_score": 0.1,
        "indoor_score":  1.0,
    }
}

# Activité nature/aventure — beau temps
check("nature + beau temps → 1.0",
      wf({"domain": "activity", "activity_type": "nature"}, good_weather) == 1.0,
      f"got {wf({'domain':'activity','activity_type':'nature'}, good_weather)}")

check("adventure + beau temps → 1.0",
      wf({"domain": "activity", "activity_type": "adventure"}, good_weather) == 1.0,
      f"got {wf({'domain':'activity','activity_type':'adventure'}, good_weather)}")

# outdoor_score=0.1 → factor = 0.70 + 0.30×0.1 = 0.73 (WEATHER_FACTOR_MIN=0.70 est le plancher à score=0.0)
_nature_bad = wf({"domain": "activity", "activity_type": "nature"}, bad_weather)
check("nature + mauvais temps → proche WEATHER_FACTOR_MIN (0.70-0.75)",
      WEATHER_FACTOR_MIN <= _nature_bad <= WEATHER_FACTOR_MIN + 0.05,
      f"got {_nature_bad}, min={WEATHER_FACTOR_MIN}")

# Culture/relax — mauvais temps dehors mais indoor ok
check("culture + pluie (indoor=1.0) → 1.0",
      wf({"domain": "activity", "activity_type": "culture"}, bad_weather) == 1.0,
      f"got {wf({'domain':'activity','activity_type':'culture'}, bad_weather)}")

check("relax + pluie (indoor=1.0) → 1.0",
      wf({"domain": "activity", "activity_type": "relax"}, bad_weather) == 1.0,
      f"got {wf({'domain':'activity','activity_type':'relax'}, bad_weather)}")

# city_experience — moyenne des deux
half_weather = {
    "available": True,
    "insights": {"outdoor_score": 0.7, "indoor_score": 0.9}
}
expected_city = WEATHER_FACTOR_MIN + (1.0 - WEATHER_FACTOR_MIN) * ((0.7 + 0.9) / 2)
city_got = wf({"domain": "activity", "activity_type": "city_experience"}, half_weather)
check("city_experience → moyenne outdoor+indoor",
      abs(city_got - expected_city) < 0.001,
      f"got {city_got}, expected {round(expected_city, 4)}")

# Domaines non-activité → neutre
for domain in ("hotel", "flight", "restaurant"):
    check(f"{domain} → 1.0 (neutre)",
          wf({"domain": domain, "activity_type": "nature"}, bad_weather) == 1.0,
          f"got {wf({'domain':domain,'activity_type':'nature'}, bad_weather)}")

# activity_type unknown → neutre
check("activity_type unknown → 1.0",
      wf({"domain": "activity", "activity_type": "unknown"}, bad_weather) == 1.0,
      f"got {wf({'domain':'activity','activity_type':'unknown'}, bad_weather)}")

check("activity_type absent → 1.0",
      wf({"domain": "activity"}, bad_weather) == 1.0,
      f"got {wf({'domain':'activity'}, bad_weather)}")

# ── D2 : BUG SILENCIEUX — weather_context unavailable (available=False) ──
# WeatherNode stocke model_dump() même quand API échoue → dict truthy
unavailable_weather = {
    "available": False,
    "city": None,
    "forecast": [],
    "insights": None,       # ← None quand API down
    "weather_summary": None,
}

wf_unavail = wf({"domain": "activity", "activity_type": "nature"}, unavailable_weather)
check(
    "weather unavailable (available=False) → 1.0 neutre [bug silencieux]",
    wf_unavail == 1.0,
    f"got {wf_unavail} (devrait être 1.0 — insights=None → défaut 0.7 → factor=0.91)"
)


# ═══════════════════════════════════════════════════════════════════════
# SECTION E — outdoor_score formula fix (weather_service.py)
# ═══════════════════════════════════════════════════════════════════════

print("\n─── E. outdoor_score formula (weather_service.py fix) ───────────")

from app.services.weather_service import WeatherService
from app.schemas.weather_schema import WeatherForecast

ws = WeatherService()

def make_forecast(temp_high, temp_low, description, wind=5.0):
    return WeatherForecast(
        date="2026-08-06",
        temperature_high=temp_high,
        temperature_low=temp_low,
        description=description,
        wind_speed=wind,
    )

# Beau temps parfait : 18-30°C + soleil + pas de pluie → outdoor_score = 1.0
perfect = ws._build_insights([make_forecast(28, 20, "ensoleillé ciel dégagé")])
check("beau temps parfait → outdoor_score = 1.0",
      perfect.outdoor_score == 1.0,
      f"got {perfect.outdoor_score}")

# Beau temps sans soleil explicite (description neutre)
warm_no_sun = ws._build_insights([make_forecast(25, 18, "partiellement nuageux")])
check("chaud sans soleil (no sun keyword) → outdoor_score ≤ 0.7",
      warm_no_sun.outdoor_score <= 0.7,
      f"got {warm_no_sun.outdoor_score}")

# Pluie + froid (hors plage 18-30°C) → outdoor_score = 0.5 - 0.4 = 0.1
# (22°C est dans [18,30] → bonus temp → 0.5+0.2-0.4=0.3 ; il faut sortir de la plage)
rainy_cold = ws._build_insights([make_forecast(10, 4, "pluie averses")])
check("pluie + froid (avg=7°C hors 18-30) → outdoor_score ≤ 0.15",
      rainy_cold.outdoor_score <= 0.15,
      f"got {rainy_cold.outdoor_score}")
# Pluie tempérée (22°C ∈ [18,30]) → bonus temp appliqué → 0.5+0.2-0.4=0.3
rainy_warm = ws._build_insights([make_forecast(22, 16, "pluie averses")])
check("pluie tempérée (22°C ∈ [18,30]) → outdoor_score = 0.3",
      abs(rainy_warm.outdoor_score - 0.3) < 0.001,
      f"got {rainy_warm.outdoor_score}")

# Soleil + pluie → annulé
sun_rain = ws._build_insights([make_forecast(24, 18, "ensoleillé averses orageuses")])
check("soleil + pluie → outdoor_score < 0.7 (pluie domine)",
      sun_rain.outdoor_score < 0.7,
      f"got {sun_rain.outdoor_score}")

# indoor_score = 1.0 quand avg_temp > 34 ET pluie
# avg > 34 nécessite (high+low)/2 > 34 → ex. 40+30=35 > 34
scorching_rain = ws._build_insights([make_forecast(40, 30, "pluie")])
check("très chaud (avg=35) + pluie → indoor_score = 1.0",
      scorching_rain.indoor_score == 1.0,
      f"got {scorching_rain.indoor_score}")
# avg_temp=(38+30)/2=34 — PAS > 34 (strict) → indoor=0.8
borderline = ws._build_insights([make_forecast(38, 30, "pluie")])
check("avg_temp=34 (égal, pas > 34) + pluie → indoor_score = 0.8",
      abs(borderline.indoor_score - 0.8) < 0.001,
      f"got {borderline.indoor_score}")

check("temps neutre → indoor_score ≥ 0.4",
      perfect.indoor_score >= 0.4,
      f"got {perfect.indoor_score}")

# Symétrie attendue : beau temps outdoor parfait = 1.0 = domaines neutres
# (l'asymétrie de l'ancien bug est corrigée)
wf_perfect = wf({"domain": "activity", "activity_type": "nature"},
                {"available": True, "insights": {"outdoor_score": perfect.outdoor_score, "indoor_score": perfect.indoor_score}})
check("beau temps parfait → weather_factor = 1.0 (symétrie restaurée)",
      wf_perfect == 1.0,
      f"got {wf_perfect}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION F — data_merger → ranking_node : flux domain + weather_factor
# ═══════════════════════════════════════════════════════════════════════

print("\n─── F. data_merger → ranking_node flux complet ─────────────────")

from app.nodes.recommendation.postprocessing.data_merger_node import DataMergerNode
from app.nodes.recommendation.postprocessing.ranking_node import RankingNode

dm = DataMergerNode()
rn = RankingNode()

# Simuler des candidats bruts (sans field domain — ajouté par data_merger)
activity_raw = {
    "id": "act_1",
    "name": "Plongée à Tabarka",
    "activity_type": "adventure",
    "user_score": 0.80,
    "business_score": 0.20,
    "is_available": None,
    "source": "mongodb",
    "tier": "external",
}
restaurant_raw = {
    "id": "rest_1",
    "name": "Dar Bibi",
    "user_score": 0.72,
    "business_score": 0.60,
    "is_available": None,
    "tier": "mongodb",
    "source": "restaurantguru",
}

# Passer par data_merger
state_dm = {
    "hotel_candidates": [],
    "flight_candidates": [],
    "restaurant_candidates": [restaurant_raw],
    "activity_candidates": [activity_raw],
    "merged_context": {"primary_intent": "day_planning"},
}
dm_result = dm.run(state_dm)
candidates = dm_result["candidates"]

check("data_merger produit 2 candidats", len(candidates) == 2,
      f"got {len(candidates)}")

check("domain='activity' posé par data_merger",
      any(c.get("domain") == "activity" for c in candidates),
      f"domains={[c.get('domain') for c in candidates]}")

check("domain='restaurant' posé par data_merger",
      any(c.get("domain") == "restaurant" for c in candidates),
      f"domains={[c.get('domain') for c in candidates]}")

# Passer par ranking_node avec météo défavorable outdoor
rn_state = {
    "candidates": candidates,
    "weather_context": bad_weather,   # outdoor_score=0.1, indoor_score=1.0
    "profile_data": {},
}
rn_result = rn.run(rn_state)
ranked = rn_result["ranked_results"]

check("ranking_node produit 2 résultats", len(ranked) == 2,
      f"got {len(ranked)}")

act = next((c for c in ranked if c.get("domain") == "activity"), None)
rest = next((c for c in ranked if c.get("domain") == "restaurant"), None)

check("activité adventure a weather_factor < 1.0 (mauvais temps)",
      act is not None and act.get("weather_factor", 1.0) < 1.0,
      f"weather_factor={act.get('weather_factor') if act else 'N/A'}")

check("restaurant a weather_factor = 1.0 (neutre, pas activité)",
      rest is not None and rest.get("weather_factor", 1.0) == 1.0,
      f"weather_factor={rest.get('weather_factor') if rest else 'N/A'}")

# Beau temps → adventure = 1.0
rn_state_good = dict(rn_state, weather_context=good_weather)
ranked_good = rn.run(rn_state_good)["ranked_results"]
act_good = next((c for c in ranked_good if c.get("domain") == "activity"), None)
check("activité adventure → weather_factor = 1.0 en beau temps",
      act_good is not None and act_good.get("weather_factor") == 1.0,
      f"weather_factor={act_good.get('weather_factor') if act_good else 'N/A'}")

# ranked_score doit être < sans météo qu'avec bonne météo
ranked_score_bad  = act.get("ranked_score",  0) if act  else 0
ranked_score_good = act_good.get("ranked_score", 0) if act_good else 0
check("ranked_score adventure beau > mauvais temps",
      ranked_score_good > ranked_score_bad,
      f"good={ranked_score_good} > bad={ranked_score_bad}")

# V2 multiplicatif invariant : user_score=0 → ranked_score=0
zero_candidate = {
    "id": "zero", "name": "Zero", "domain": "activity",
    "activity_type": "nature", "user_score": 0.0,
    "business_score": 0.9, "is_available": True,
    "source": "agency", "tier": "partner",
}
rn_zero = rn.run({"candidates": [zero_candidate], "weather_context": good_weather, "profile_data": {}})
check("user_score=0 → ranked_score=0 (invariant V2)",
      rn_zero["ranked_results"][0]["ranked_score"] == 0.0,
      f"got {rn_zero['ranked_results'][0]['ranked_score']}")


# ═══════════════════════════════════════════════════════════════════════
# RÉCAPITULATIF
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "═" * 62)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total  = len(results)
print(f"  RÉSULTAT : {passed}/{total} PASS  |  {failed} FAIL")

if failed > 0:
    print("\n  Checks échoués :")
    for name, ok in results:
        if not ok:
            print(f"    ❌  {name}")

print("═" * 62)
sys.exit(0 if failed == 0 else 1)
