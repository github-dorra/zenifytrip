# -*- coding: utf-8 -*-
"""
DaySkeletonNode — squelette de journée instantané (Python pur, aucun LLM)
==========================================================================
Construit la STRUCTURE de la journée depuis trip_position + booking_anchors :
ancres immuables posées (repas inclus, services bookés, logistique départ),
slots ouverts marqués "open" — remplis ensuite par day_planner.

Émis immédiatement (<10ms) → affiché au user pendant que le pipeline tourne.
Bypass propre pour les intents hors day_planning/trip_package.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.utils.time_utils import hour_of

DAY_SKELETON_INTENTS = {"day_planning", "trip_package_recommendation"}

# Labels des créneaux — langue depuis intent_result.language (fallback fr)
_SLOT_LABELS = {
    "fr": {"breakfast": "Petit-déjeuner", "morning": "Matin", "lunch": "Déjeuner",
           "afternoon": "Après-midi", "evening": "Soir", "dinner": "Dîner",
           "logistics": "Logistique départ", "arrival": "Arrivée"},
    "en": {"breakfast": "Breakfast", "morning": "Morning", "lunch": "Lunch",
           "afternoon": "Afternoon", "evening": "Evening", "dinner": "Dinner",
           "logistics": "Departure logistics", "arrival": "Arrival"},
    "ar": {"breakfast": "الفطور", "morning": "الصباح", "lunch": "الغداء",
           "afternoon": "بعد الظهر", "evening": "المساء", "dinner": "العشاء",
           "logistics": "ترتيبات المغادرة", "arrival": "الوصول"},
}

_TEXTS = {
    "fr": {"header": "📅 Votre journée à {dest}", "day_of": " — jour {i}/{n}",
           "day_sep": "— Jour {n} —",            "pending": "… en cours de sélection",
           "meal_included": "{label} inclus à l'hôtel",
           "arrival_checkin": "Arrivée + check-in hôtel",
           "checkout_transfer": "Check-out + transfert aéroport",
           "already_booked": "{name} — déjà réservé ✓"},
    "en": {"header": "📅 Your day in {dest}",    "day_of": " — day {i}/{n}",
           "day_sep": "— Day {n} —",             "pending": "… being selected",
           "meal_included": "{label} included at your hotel",
           "arrival_checkin": "Arrival + hotel check-in",
           "checkout_transfer": "Check-out + airport transfer",
           "already_booked": "{name} — already booked ✓"},
    "ar": {"header": "📅 يومك في {dest}",         "day_of": " — اليوم {i}/{n}",
           "day_sep": "— اليوم {n} —",           "pending": "قيد الاختيار…",
           "meal_included": "{label} مشمول في فندقك",
           "arrival_checkin": "الوصول وتسجيل الدخول في الفندق",
           "checkout_transfer": "تسجيل المغادرة والنقل إلى المطار",
           "already_booked": "{name} — محجوز مسبقًا"},
}
# es/de non fournis → fallback fr (extensibles ici sans toucher au code)

_ICONS = {"breakfast": "🍳", "morning": "🌅", "lunch": "🍽️", "afternoon": "🏛️",
          "evening": "🌆", "dinner": "🍽️", "logistics": "🧳", "arrival": "✈️"}


class DaySkeletonNode(BaseNode):

    def __init__(self):
        super().__init__(NodeConfig(name="day_skeleton", node_type="technical"))

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        intent = (state.get("intent_result") or {}).get("primary_intent", "")
        if intent not in DAY_SKELETON_INTENTS:
            return {"day_skeleton": None}

        trip        = state.get("trip_position")       or {}
        anchors     = state.get("booking_anchors")     or {}
        merged      = state.get("merged_context")      or {}
        avail       = state.get("availability_result") or {}
        constraints = (state.get("intent_result") or {}).get("constraints") or {}

        language = (state.get("intent_result") or {}).get("language", "fr")
        labels   = _SLOT_LABELS.get(language, _SLOT_LABELS["fr"])
        texts    = _TEXTS.get(language, _TEXTS["fr"])

        duration  = self._resolve_duration(merged, avail)
        start     = self._resolve_start_date(constraints)
        outbound  = str(avail.get("outbound_date") or "")[:10] or None
        return_d  = str(avail.get("return_date")   or "")[:10] or None
        arrival_h = hour_of(trip.get("arrival_time"))

        days = []
        for n in range(duration):
            day_date = (start + timedelta(days=n)).isoformat() if start else None
            mode  = self._mode_for_date(day_date, outbound, return_d, arrival_h)
            slots = self._build_slots(mode, anchors, day_date, labels, texts)
            days.append({"day_number": n + 1, "date": day_date, "mode": mode, "slots": slots})

        skeleton = {
            "destination":   merged.get("destination") or "Tunisie",
            "duration_days": duration,
            "day_context": {
                "day_index":    trip.get("day_index"),
                "total_days":   trip.get("total_days"),
                "is_first_day": trip.get("is_first_day", False),
                "is_last_day":  trip.get("is_last_day", False),
            },
            "days":         days,
            "display_text": self._render(merged.get("destination"), trip, days, labels, texts),
        }
        self.logger.info(
            f"[DaySkeleton] {duration} jour(s) | lang={language} | mode_j1={days[0]['mode']} | "
            f"ancres={sum(1 for d in days for s in d['slots'] if s['status'] == 'anchored')}"
        )
        return {"day_skeleton": skeleton}

    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_duration(merged: Dict, avail: Dict) -> int:
        if avail.get("trip_is_ongoing") and avail.get("days_remaining") is not None:
            base  = max(1, int(avail["days_remaining"]))
            asked = merged.get("duration_days")
            return min(base, int(asked)) if asked else 1   # "plan my day" = 1 jour par défaut
        try:
            return max(1, int(merged.get("duration_days") or 1))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _resolve_start_date(constraints: Dict) -> Optional[date]:
        # Date EXPLICITE de l'utilisateur uniquement — merged.start_date est pollué
        # par l'outbound_date du contrat (context_merger) et planifierait le J1 du séjour.
        # Même règle que check_availability (request_date = constraints ou today).
        raw = str(constraints.get("start_date") or "")[:10]
        try:
            return date.fromisoformat(raw) if raw else date.today()
        except ValueError:
            return date.today()

    @staticmethod
    def _mode_for_date(day_date: Optional[str], outbound: Optional[str],
                       return_d: Optional[str], arrival_h: int) -> str:
        """Mode déterministe par jour — mêmes règles que SITUATION AWARENESS du prompt."""
        if day_date and return_d and day_date == return_d:
            return "morning_only_departure"
        if day_date and outbound and day_date == outbound:
            if arrival_h >= 15:
                return "evening_only"
            if 0 <= arrival_h < 12:
                return "half_day_morning_arrival"
        return "full_day"

    def _build_slots(self, mode: str, anchors: Dict, day_date: Optional[str],
                     labels: Dict, texts: Dict) -> List[Dict]:
        """Ancres posées, slots ouverts marqués — jamais de contenu inventé."""
        breakfast = anchors.get("breakfast_included")
        lunch     = anchors.get("lunch_included")
        dinner    = anchors.get("dinner_included")
        booked    = self._booked_for(anchors, day_date)

        def meal(slot: str, included) -> Dict:
            if included is True:
                return {"time_slot": slot, "status": "anchored", "item_type": "meal_included",
                        "name": texts["meal_included"].format(label=labels.get(slot, slot))}
            return {"time_slot": slot, "status": "open", "item_type": None, "name": None}

        if mode == "evening_only":
            return [
                {"time_slot": "arrival", "status": "anchored", "item_type": "logistics",
                 "name": texts["arrival_checkin"]},
                {"time_slot": "evening", "status": "open", "item_type": None, "name": None},
            ]

        if mode == "morning_only_departure":
            slots = []
            if breakfast is True:
                slots.append(meal("breakfast", True))
            slots.append({"time_slot": "morning", "status": "open", "item_type": None, "name": None})
            slots.append({"time_slot": "logistics", "status": "anchored", "item_type": "logistics",
                          "name": texts["checkout_transfer"]})
            return slots

        if mode == "half_day_morning_arrival":
            return [
                {"time_slot": "morning", "status": "open", "item_type": None, "name": None},
                meal("lunch", lunch),
                {"time_slot": "afternoon", "status": "open", "item_type": None, "name": None},
            ]

        # full_day
        slots = []
        if breakfast is True:
            slots.append(meal("breakfast", True))
        slots.append({"time_slot": "morning", "status": "open", "item_type": None, "name": None})
        slots.append(meal("lunch", lunch))
        if booked:
            slots.append({"time_slot": "afternoon", "status": "anchored",
                          "item_type": "booked_service",
                          "name": texts["already_booked"].format(name=booked.get("name", ""))})
        else:
            slots.append({"time_slot": "afternoon", "status": "open", "item_type": None, "name": None})
        slots.append(meal("dinner" if dinner is True else "evening", dinner))
        return slots

    @staticmethod
    def _booked_for(anchors: Dict, day_date: Optional[str]) -> Optional[Dict]:
        if not day_date:
            return None
        for s in anchors.get("booked_services") or []:
            if str(s.get("date") or "")[:10] == day_date and s.get("status") != "Cancelled":
                return s
        return None

    @staticmethod
    def _render(destination: Optional[str], trip: Dict, days: List[Dict],
                labels: Dict, texts: Dict) -> str:
        """Texte squelette affiché immédiatement au user (étape ⑦ stream)."""
        header = texts["header"].format(dest=destination or "—")
        if trip.get("day_index"):
            header += texts["day_of"].format(i=trip["day_index"], n=trip["total_days"])
        lines = [header]
        for d in days:
            if len(days) > 1:
                lines.append(texts["day_sep"].format(n=d["day_number"]))
            for s in d["slots"]:
                icon    = _ICONS.get(s["time_slot"], "•")
                content = s["name"] if s["status"] == "anchored" else texts["pending"]
                lines.append(f"  {icon} {labels.get(s['time_slot'], s['time_slot'])} : {content}")
        return "\n".join(lines)
