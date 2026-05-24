# semantic_agent_node_final_production.py   #app.test.py

"""
Outputs:
- semantic_query: Natural language search query (max 50 chars)
- global_keywords: Intent-aligned keywords (max 8)
- contextual_keywords: Contextual trip keywords (max 8)
- semantic_metadata
- semantic_cache_key

KEY FEATURES:
- Intent-driven keyword validation
- Strict camelCase validation
- Deduplication
- Cache optimization
"""

from typing import Dict, Any, List, Optional
from app.nodes.core.Base_node import BaseNode
from app.nodes.definitions import SEMANTIC_CONFIG
from app.prompts.recommendation.semantic_prompt import (
    SEMANTIC_SYSTEM_PROMPT
)
from app.nodes.utility.json_parser import parse_json_safely

import hashlib
import json
import logging
import time
import re


class SemanticAgentNode(BaseNode):

    CAMEL_CASE_PATTERN = re.compile(
        r"^[a-zA-Z0-9][a-zA-Z0-9]*$"
    )

    # =========================================================
    # INTENT KEYWORD POOLS
    # =========================================================

    INTENT_KEYWORD_POOLS = {

        "accommodation_recommendation": {
            "domain": "accommodation",
            "keywords": {
                "familyResort",
                "beachfrontHotel",
                "kidsFriendlyHotel",
                "budgetHotel",
                "allInclusive",
                "familyRoom",
                "beachResort",
                "relaxingHotel",
                "mountainResort",
                "luxuryHotel",
                "boutiqueHotel",
                "cityHotel",
                "poolResort",
                "golfResort",
                "spaResort",
                "ecoLodge",
                "roomWithView",
                "villasResort",
                "houseRental"
            }
        },

        "activity_recommendation": {
            "domain": "activity",
            "keywords": {
                "waterActivity",
                "beachActivity",
                "mountaineering",
                "historicalSites",
                "culturalActivity",
                "sightseeing",
                "adventureSports",
                "foodieExperience",
                "shoppingTrip",
                "nightlife",
                "museumVisit",
                "artGallery",
                "localCulture",
                "spiritualExperience",
                "outdoorActivity",
                "indoorActivity",
                "familyActivity",
                "wildlifeSafari",
                "watersports",
                "hikingTrail",
                "boatTour",
                "zipline",
                "skydiving",
                "caveExploration",
                "gardensVisit",
                "theaterShow",
                "concerts",
                "shopping"
            }
        },

        "restaurant_recommendation": {
            "domain": "restaurant",
            "keywords": {
                "localCuisine",
                "gastronomyFocus",
                "streetFood",
                "michelinRestaurant",
                "familyRestaurant",
                "budgetEating",
                "seafoodRestaurant",
                "vegetarianFood",
                "halalFood",
                "kosherFood",
                "rooftopDining",
                "beachbarDining",
                "traditionalCuisine",
                "modernCuisine",
                "romanticDining",
                "quietCafe",
                "foodCourt",
                "beachFrontEating",
                "hillviewDining",
                "fineRestaurant"
            }
        },

        "flight_recommendation": {
            "domain": "flight",
            "keywords": {
                "directFlight",
                "economyClass",
                "businessClass",
                "firstClass",
                "shortHaul",
                "longHaul",
                "morningFlight",
                "eveningFlight",
                "earlyBirdFlight",
                "nightFlight",
                "stopover",
                "laidBackTravel",
                "luxuryTravel",
                "fastestRoute",
                "cheapestTicket",
                "premiumAirline",
                "budgetAirline",
                "familyFriendlyAirline"
            }
        },

        "day_planning": {
            "domain": "dayplan",
            "keywords": {
                "morningActivity",
                "afternoonActivity",
                "eveningActivity",
                "quickGetaway",
                "slowPace",
                "moderatePace",
                "fastPace",
                "compactItinerary",
                "relaxedSchedule",
                "familyFriendlyTiming",
                "childrenRest",
                "mealTimes",
                "siestaPause"
            }
        },

        "trip_package_recommendation": {
            "domain": "package",
            "keywords": "ALL"
        },

        "travel_question": {
            "domain": "info",
            "keywords": {
                "bestTimeToVisit",
                "weatherInfo",
                "budgetInfo",
                "visaInfo",
                "culturalInfo",
                "safetyInfo",
                "transportInfo"
            }
        },
    }

    # =========================================================
    # UNIVERSAL CONTEXTUAL KEYWORDS
    # =========================================================

    UNIVERSAL_CONTEXTUAL = {
        "destination",
        "duration",
        "budget",
        "weather",
        "season",
        "pace",

        "tunis",
        "mahdia",
        "elJam",
        "monastir",
        "djerba",
        "beja",
        "sousse",

        "1day",
        "2days",
        "3days",
        "5days",
        "7days",
        "14days",

        "budgetFriendly",
        "mediumBudget",
        "luxuryBudget",

        "sunny",
        "rainy",
        "cloudy",
        "hot",
        "cold",

        "spring",
        "summer",
        "autumn",
        "winter",

        "quickGetaway",
        "weeklyTrip",
        "deepExploration"
    }

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self):

        super().__init__(SEMANTIC_CONFIG)

        self.logger = logging.getLogger(__name__)

    # =========================================================
    # MAIN RUN
    # =========================================================

    def run(
        self,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:

        start_time = time.time()

        user_message = state.get("user_message", "")

        merged_context = state.get(
            "merged_context",
            {}
        )

        weather_context = state.get(
            "weather_context",
            {}
        )

        # -----------------------------------------------------

        if not merged_context:

            self.logger.warning(
                "No merged_context in semantic agent"
            )

            return self._return_empty_semantic()

        # =====================================================
        # PRIMARY INTENT
        # =====================================================

        primary_intent = merged_context.get(
            "primary_intent",
            "unsupported"
        )

        secondary_intents = merged_context.get(
            "secondary_intents",
            []
        )

        intent_config = self.INTENT_KEYWORD_POOLS.get(
            primary_intent,
            {
                "domain": "unknown",
                "keywords": set()
            }
        )

        domain = intent_config.get(
            "domain",
            "unknown"
        )

        allowed_keywords = intent_config.get(
            "keywords",
            set()
        )

        self.logger.info(
            f"Semantic: "
            f"intent={primary_intent}, "
            f"domain={domain}"
        )

        # =====================================================
        # CONTEXT
        # =====================================================

        merged_data = {
            "destination": merged_context.get(
                "destination"
            ),

            "travelers": merged_context.get(
                "travelers"
            ),

            "is_family": merged_context.get(
                "is_family",
                False
            ),

            "duration_days": merged_context.get(
                "duration_days"
            ),

            "budget_level": merged_context.get(
                "budget_level"
            ),

            "interests": merged_context.get(
                "interests",
                []
            ),

            "primary_intent": primary_intent,

            "secondary_intents": secondary_intents,
        }

        weather_insights = weather_context.get(
            "insights",
            {}
        )

        weather_data = {
            "avg_temperature":
                weather_insights.get(
                    "avg_temperature"
                ),

            "is_hot_day":
                weather_insights.get(
                    "is_hot_day",
                    False
                ),

            "is_rainy_day":
                weather_insights.get(
                    "is_rainy_day",
                    False
                ),

            "is_sunny_day":
                weather_insights.get(
                    "is_sunny_day",
                    False
                ),

            "beach_score":
                weather_insights.get(
                    "beach_score"
                ),

            "outdoor_score":
                weather_insights.get(
                    "outdoor_score"
                ),

            "indoor_score":
                weather_insights.get(
                    "indoor_score"
                ),

            "recommendation_hint":
                weather_insights.get(
                    "recommendation_hint"
                ),
        }

        # BUILD PROMPT

        prompt = SEMANTIC_SYSTEM_PROMPT.format(
            user_message=user_message,
            merged_context=json.dumps(merged_data, ensure_ascii=False),
            weather_context=json.dumps(weather_data, ensure_ascii=False),
        )

        
        # CALL LLM

        raw_response = ""

        try:

            response = self.call_llm(
                prompt=prompt
            )

            raw_response = response.get(
                "content",
                ""
            )

            data = parse_json_safely(
                raw_response
            )

            if not isinstance(data, dict):
                raise ValueError(
                    "Invalid JSON structure"
                )

        except Exception as e:

            self.logger.error(
                f"Semantic LLM error: "
                f"{type(e).__name__}: {e}"
            )
            self.logger.info(f"RAW LLM OUTPUT:\n{raw_response}")

            return self._return_empty_semantic()

        # =====================================================
        # VALIDATION
        # =====================================================

        semantic_query = self._validate_query(
            data.get(
                "semantic_query",
                ""
            )
        )

        global_keywords = self._validate_keywords(
            keywords=data.get(
                "global_keywords",
                []
            ),

            max_count=8,

            allowed=allowed_keywords,

            intent_domain=domain,
        )

        contextual_keywords = self._validate_keywords(
            keywords=data.get(
                "contextual_keywords",
                []
            ),

            max_count=8,

            allowed=self.UNIVERSAL_CONTEXTUAL,

            intent_domain="contextual",
        )

        # =====================================================
        # METADATA
        # =====================================================

        metadata = data.get(
            "metadata",
            {}
        )

        if not isinstance(metadata, dict):
            metadata = {}

        metadata["intent_domain"] = domain
        metadata["primary_intent"] = primary_intent

        # =====================================================
        # CACHE KEY
        # =====================================================

        cache_key = self._create_cache_key(
            destination=merged_context.get(
                "destination"
            ),

            duration=merged_context.get(
                "duration_days"
            ),

            intent=primary_intent,

            keywords=(
                global_keywords +
                contextual_keywords
            )
        )

        # =====================================================
        # LOG
        # =====================================================

        elapsed = time.time() - start_time

        self.logger.info(
            f"Semantic complete "
            f"({elapsed*1000:.0f}ms): "
            f"{len(global_keywords)} global / "
            f"{len(contextual_keywords)} contextual"
        )

        # =====================================================
        # RETURN
        # =====================================================

        return {
            "semantic_query": semantic_query,
            "global_keywords": global_keywords,
            "contextual_keywords": contextual_keywords,
            "semantic_metadata": metadata,
            "semantic_cache_key": cache_key,
        }

    # =========================================================
    # VALIDATION HELPERS
    # =========================================================

    def _validate_query(
        self,
        query: str
    ) -> Optional[str]:

        if not query or not isinstance(query, str):
            return None

        query = " ".join(
            query.strip().split()
        )

        if len(query) > 50:
            truncated = query[:50]
            last_space = truncated.rfind(" ")
            query = truncated[:last_space] if last_space > 0 else truncated

        return query if query else None

    # =========================================================

    def _validate_keywords(
        self,
        keywords: Any,
        max_count: int = 8,
        allowed: Any = None,
        intent_domain: str = "unknown",
    ) -> List[str]:

        # -----------------------------------------------------
        # Ensure list
        # -----------------------------------------------------

        if not isinstance(keywords, list):
            keywords = [keywords] if keywords else []

        # -----------------------------------------------------
        # Normalize
        # -----------------------------------------------------

        keywords = [
            str(k).strip()
            for k in keywords
            if isinstance(k, str) and k.strip()
        ]

        validated = []

        # -----------------------------------------------------
        # Validation
        # -----------------------------------------------------

        for keyword in keywords:

            # format validation
            if not self._is_valid_keyword_format(
                keyword
            ):

                self.logger.warning(
                    f"Invalid keyword format: "
                    f"{keyword}"
                )

                continue

            # allowed pool validation (case-insensitive)
            if allowed and allowed != "ALL":

                allowed_lower = {k.lower() for k in allowed}

                if keyword.lower() not in allowed_lower:

                    self.logger.warning(
                        f"Keyword '{keyword}' "
                        f"not allowed for "
                        f"domain '{intent_domain}'"
                    )

                    continue

            validated.append(keyword)

        # -----------------------------------------------------
        # Remove duplicates preserving order
        # -----------------------------------------------------

        seen = set()

        unique = []

        for keyword in validated:

            if keyword not in seen:

                unique.append(keyword)

                seen.add(keyword)

        validated = unique

        # -----------------------------------------------------
        # Enforce max count
        # -----------------------------------------------------

        if len(validated) > max_count:

            self.logger.warning(
                f"Keywords truncated "
                f"to max {max_count}"
            )

            validated = validated[:max_count]

        return validated

    # =========================================================

    def _is_valid_keyword_format(
        self,
        keyword: str
    ) -> bool:
        """
        camelCase validation only
        """

        return bool(
            self.CAMEL_CASE_PATTERN.match(
                keyword
            )
        )

    # =========================================================

    def _create_cache_key(
        self,
        destination: Optional[str],
        duration: Optional[int],
        intent: Optional[str],
        keywords: List[str]
    ) -> str:

        key_parts = {

            "dest": (
                destination or "unknown"
            ).lower(),

            "dur": duration or 0,

            "intent": intent or "unknown",

            "kw": sorted(keywords)[:6]
        }

        key_str = json.dumps(
            key_parts,
            sort_keys=True,
            ensure_ascii=False
        )

        hash_obj = hashlib.sha256(
            key_str.encode("utf-8")
        )

        return hash_obj.hexdigest()[:16]

    # =========================================================

    def _return_empty_semantic(
        self
    ) -> Dict[str, Any]:

        return {

            "semantic_query": None,

            "global_keywords": [],

            "contextual_keywords": [],

            "semantic_metadata": {},

            "semantic_cache_key": None,
        }