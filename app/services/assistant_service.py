"""AI Assistant orchestration service (Section 8.14)."""

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from app.assistant.facts import (
    FactsBundle,
    build_facts_json,
    build_user_reports_block,
    extract_allowed_numbers,
)
from app.assistant.fallback import build_quick_reply
from app.assistant.gemini_client import GeminiClient
from app.assistant.intents import Intent
from app.assistant.parser import ParsedMessage, parse_message
from app.assistant.prompts import build_user_content
from app.assistant.quota import QuotaManager
from app.assistant.safety import build_static_reply
from app.assistant.tools import (
    run_activity_tool,
    run_air_tool,
    run_explain_tool,
    run_home_tips_tool,
    run_reports_tool,
    run_route_tool,
)
from app.assistant.validator import validate_draft
from app.config import Settings
from app.constants import ASSISTANT_CACHE_TTL, HOME_TIPS_CACHE_TTL
from app.core.cache import get_or_set
from app.domain.models import LatLon, Scale, SensitiveGroup
from app.providers.base import GeocodeProvider
from app.services.air_service import AirService
from app.services.report_service import ReportService
from app.services.route_service import RouteService
from app.storage.base import StoreProtocol

logger = logging.getLogger("breathemap.assistant")

_INTENT_CACHE_TTL: dict[Intent, int] = {
    Intent.AIR_NOW: ASSISTANT_CACHE_TTL,
    Intent.BEST_TIME: ASSISTANT_CACHE_TTL,
    Intent.ACTIVITY_ADVICE: ASSISTANT_CACHE_TTL,
    Intent.ROUTE_COMPARE: 900,
    Intent.HOME_TIPS: HOME_TIPS_CACHE_TTL,
    Intent.EXPLAIN: HOME_TIPS_CACHE_TTL,
    Intent.REPORTS_NEARBY: 300,
}


def _build_cache_key(
    *,
    intent: Intent,
    lat: float | None,
    lon: float | None,
    dep_time: datetime | None,
    dest_key: str,
    activity: str | None,
    duration_min: int | None,
    sensitive: list[SensitiveGroup],
    scale: Scale,
    is_demo: bool,
    ai_eligible: bool,
    now: datetime,
) -> str:
    bucket_30m = int((dep_time or now).timestamp() // 1800)
    raw = json.dumps(
        {
            "intent": intent.value,
            "lat": round(lat, 2) if lat is not None else None,
            "lon": round(lon, 2) if lon is not None else None,
            "bucket": bucket_30m,
            "dest": dest_key.lower(),
            "act": activity,
            "dur": duration_min,
            "sens": sorted(s.value for s in sensitive),
            "scale": scale.value,
            "demo": is_demo,
            "ai": ai_eligible,
        },
        sort_keys=True,
    )
    return "assistant:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clarify_response(
    *,
    intent: Intent,
    question: str,
    chips: list[dict[str, Any]],
    resolved_context: dict[str, Any],
    is_demo: bool,
) -> dict[str, Any]:
    return {
        "reply": {
            "summary": question,
            "recommendation": "Choose an option below or type your answer.",
            "reasons": [],
            "caveats": [],
        },
        "answer_mode": "clarify",
        "cards": [],
        "chips": chips,
        "resolved_context": {"intent": intent.value, **resolved_context},
        "provenance": {"source": "BreatheMap", "is_demo": is_demo, "cached": False},
    }


class AssistantService:
    """Orchestrates parsing, slot filling, deterministic tools, Gemini, and caching."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: StoreProtocol,
        air_service: AirService,
        route_service: RouteService,
        report_service: ReportService,
        geo_provider: GeocodeProvider,
        gemini_client: GeminiClient,
    ) -> None:
        self.settings = settings
        self.store = store
        self.air_service = air_service
        self.route_service = route_service
        self.report_service = report_service
        self.geo_provider = geo_provider
        self.gemini_client = gemini_client
        self.quota = QuotaManager(store, settings)

    def _check_missing_slots(
        self,
        parsed: ParsedMessage,
        *,
        lat: float | None,
        lon: float | None,
        context: dict[str, Any],
        is_demo: bool,
    ) -> dict[str, Any] | None:
        """Return a clarification response (0 Gemini calls) if required slots are missing."""
        needs_location = parsed.intent in {
            Intent.AIR_NOW,
            Intent.BEST_TIME,
            Intent.ACTIVITY_ADVICE,
            Intent.ROUTE_COMPARE,
            Intent.HOME_TIPS,
            Intent.REPORTS_NEARBY,
            Intent.REPORT_HELP,
        }
        resolved_base = {
            "departure_time": parsed.departure_time.isoformat() if parsed.departure_time else None,
            "duration_min": parsed.duration_min,
            "mode": parsed.mode.value if parsed.mode else None,
            "activity": parsed.activity,
        }

        if needs_location and (lat is None or lon is None):
            return _clarify_response(
                intent=parsed.intent,
                question="Where are you located?",
                chips=[
                    {"label": "Use my location", "action": "use_location"},
                    {"label": "Try Delhi demo", "action": "use_demo"},
                ],
                resolved_context=resolved_base,
                is_demo=is_demo,
            )

        if parsed.intent == Intent.ACTIVITY_ADVICE:
            if parsed.departure_time is None:
                return _clarify_response(
                    intent=parsed.intent,
                    question="When are you planning to go out?",
                    chips=[
                        {"label": "Now", "action": "set_time", "value": "now"},
                        {"label": "In 1 hour", "action": "set_time", "value": "in 1 hour"},
                        {"label": "This evening", "action": "set_time", "value": "this evening"},
                    ],
                    resolved_context=resolved_base,
                    is_demo=is_demo,
                )
            if parsed.duration_min is None:
                return _clarify_response(
                    intent=parsed.intent,
                    question="How long do you plan to be out?",
                    chips=[
                        {"label": "20 min", "action": "set_duration", "value": 20},
                        {"label": "30 min", "action": "set_duration", "value": 30},
                        {"label": "45 min", "action": "set_duration", "value": 45},
                        {"label": "1 hour", "action": "set_duration", "value": 60},
                    ],
                    resolved_context=resolved_base,
                    is_demo=is_demo,
                )

        if parsed.intent == Intent.ROUTE_COMPARE:
            has_dest = bool(parsed.destination_text or context.get("destination"))
            if not has_dest:
                return _clarify_response(
                    intent=parsed.intent,
                    question="Where are you heading?",
                    chips=[
                        {"label": "India Gate", "action": "set_destination", "value": "India Gate"},
                        {
                            "label": "New Delhi Railway Station",
                            "action": "set_destination",
                            "value": "New Delhi Railway Station",
                        },
                    ],
                    resolved_context=resolved_base,
                    is_demo=is_demo,
                )
            if parsed.departure_time is None:
                return _clarify_response(
                    intent=parsed.intent,
                    question="When are you leaving?",
                    chips=[
                        {"label": "Now", "action": "set_time", "value": "now"},
                        {"label": "In 1 hour", "action": "set_time", "value": "in 1 hour"},
                        {"label": "This evening", "action": "set_time", "value": "this evening"},
                    ],
                    resolved_context=resolved_base,
                    is_demo=is_demo,
                )

        return None

    async def _resolve_route_destination(
        self,
        parsed: ParsedMessage,
        context: dict[str, Any],
        is_demo: bool,
    ) -> tuple[LatLon | None, dict[str, Any] | None]:
        raw_dest = context.get("destination")
        if isinstance(raw_dest, dict) and "lat" in raw_dest and "lon" in raw_dest:
            return LatLon(lat=float(raw_dest["lat"]), lon=float(raw_dest["lon"])), None
        if parsed.destination_text:
            matches = await self.geo_provider.search(parsed.destination_text)
            if not matches:
                return None, _clarify_response(
                    intent=parsed.intent,
                    question=(
                        f"No places found for '{parsed.destination_text}'. "
                        "Try a nearby landmark or area name."
                    ),
                    chips=[],
                    resolved_context={"intent": parsed.intent.value},
                    is_demo=is_demo,
                )
            first = matches[0]
            return LatLon(lat=float(first["lat"]), lon=float(first["lon"])), None
        return None, None

    async def _run_intent_tools(
        self,
        parsed: ParsedMessage,
        *,
        lat: float,
        lon: float,
        scale: Scale,
        sensitive: list[SensitiveGroup],
        context: dict[str, Any],
        is_demo: bool,
        bundle: FactsBundle,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Run deterministic domain/service tools for the parsed intent."""
        if parsed.intent == Intent.AIR_NOW:
            _, cards = await run_air_tool(
                self.air_service,
                lat=lat,
                lon=lon,
                scale=scale,
                is_demo=is_demo,
                bundle=bundle,
                include_windows=False,
            )
            return cards, None

        if parsed.intent == Intent.BEST_TIME:
            _, cards = await run_air_tool(
                self.air_service,
                lat=lat,
                lon=lon,
                scale=scale,
                is_demo=is_demo,
                bundle=bundle,
                include_windows=True,
            )
            return cards, None

        if parsed.intent == Intent.ACTIVITY_ADVICE:
            cards = await run_activity_tool(
                self.air_service,
                lat=lat,
                lon=lon,
                scale=scale,
                activity_str=parsed.activity or "walk",
                duration_min=parsed.duration_min or 30,
                sensitive=sensitive,
                is_demo=is_demo,
                bundle=bundle,
            )
            return cards, None

        if parsed.intent == Intent.ROUTE_COMPARE:
            dest_coord, clarify_err = await self._resolve_route_destination(
                parsed, context, is_demo
            )
            if clarify_err is not None:
                return [], clarify_err

            modes = [parsed.mode] if parsed.mode else None
            _, cards = await run_route_tool(
                self.route_service,
                origin_lat=lat,
                origin_lon=lon,
                destination=dest_coord,
                destination_text=parsed.destination_text,
                departure_time=parsed.departure_time,
                modes=modes,
                sensitive=sensitive,
                scale=scale,
                is_demo=is_demo,
                bundle=bundle,
            )
            return cards, None

        if parsed.intent == Intent.HOME_TIPS:
            cards = await run_home_tips_tool(
                self.air_service,
                lat=lat,
                lon=lon,
                scale=scale,
                is_demo=is_demo,
                bundle=bundle,
            )
            return cards, None

        if parsed.intent == Intent.REPORTS_NEARBY:
            cards = await run_reports_tool(
                self.report_service,
                lat=lat,
                lon=lon,
                is_demo=is_demo,
                bundle=bundle,
            )
            return cards, None

        if parsed.intent == Intent.EXPLAIN:
            return run_explain_tool(parsed.topic, bundle), None

        return [], None

    async def chat(
        self,
        *,
        message: str,
        context: dict[str, Any] | None = None,
        recent_turns: list[str] | None = None,
        reporter_hash: str,
        is_demo: bool = False,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Execute the full assistant pipeline and return (response_data, cached)."""
        t0 = time.monotonic()
        ref_now = now or datetime.now(UTC)
        ctx = context or {}
        tz_name = str(ctx.get("timezone") or "Asia/Kolkata")
        parsed = parse_message(message, ctx, now=ref_now, tz_name=tz_name)

        # 1. Static intents (zero Gemini calls)
        if parsed.intent in {
            Intent.EMERGENCY,
            Intent.MEDICAL,
            Intent.OUT_OF_SCOPE,
            Intent.GREETING,
        }:
            reply = build_static_reply(parsed.intent, country_code=ctx.get("country_code"))
            payload = {
                "reply": reply,
                "answer_mode": "static",
                "cards": [],
                "chips": [],
                "resolved_context": {"intent": parsed.intent.value},
                "provenance": {"source": "BreatheMap", "is_demo": is_demo, "cached": False},
            }
            self._log_turn(parsed.intent, "static", False, False, "static_intent", t0)
            return payload, False

        lat = float(ctx["lat"]) if ctx.get("lat") is not None else None
        lon = float(ctx["lon"]) if ctx.get("lon") is not None else None

        # 2. Missing slots -> clarify (zero Gemini calls)
        clarify = self._check_missing_slots(parsed, lat=lat, lon=lon, context=ctx, is_demo=is_demo)
        if clarify is not None:
            self._log_turn(parsed.intent, "clarify", False, False, "missing_slot", t0)
            return clarify, False

        # 3. Report help -> link only, never posts (zero Gemini calls)
        if parsed.intent == Intent.REPORT_HELP:
            reply = build_quick_reply(Intent.REPORT_HELP, cards=[])
            help_payload: dict[str, Any] = {
                "reply": reply,
                "answer_mode": "quick",
                "cards": [],
                "chips": [{"label": "Open BreatheWatch form", "action": "open_watch"}],
                "resolved_context": {"intent": parsed.intent.value, "lat": lat, "lon": lon},
                "provenance": {"source": "BreatheMap", "is_demo": is_demo, "cached": False},
            }
            self._log_turn(parsed.intent, "quick", False, False, "report_help", t0)
            return help_payload, False

        safe_lat = lat if lat is not None else 28.6315
        safe_lon = lon if lon is not None else 77.2167
        scale = Scale(str(ctx.get("scale", "naqi")))
        sensitive: list[SensitiveGroup] = []
        for s in ctx.get("sensitive", []):
            try:
                sensitive.append(SensitiveGroup(str(s)))
            except ValueError:
                continue

        # 4. Cache lookup
        dest_key = parsed.destination_text or str(parsed.topic or "")
        cache_key = _build_cache_key(
            intent=parsed.intent,
            lat=safe_lat,
            lon=safe_lon,
            dep_time=parsed.departure_time,
            dest_key=dest_key,
            activity=parsed.activity,
            duration_min=parsed.duration_min,
            sensitive=sensitive,
            scale=scale,
            is_demo=is_demo,
            ai_eligible=bool(self.settings.GEMINI_ENABLED and self.settings.GEMINI_API_KEY),
            now=ref_now,
        )
        ttl = _INTENT_CACHE_TTL.get(parsed.intent, ASSISTANT_CACHE_TTL)

        computed = False

        async def _compute() -> dict[str, Any]:
            nonlocal computed
            computed = True
            return await self._execute_tools_and_llm(
                message=message,
                parsed=parsed,
                recent_turns=recent_turns or [],
                lat=safe_lat,
                lon=safe_lon,
                scale=scale,
                sensitive=sensitive,
                context=ctx,
                reporter_hash=reporter_hash,
                is_demo=is_demo,
                ref_now=ref_now,
            )

        result = await get_or_set(self.store, cache_key, ttl, _compute)
        cached_before = not computed
        if cached_before:
            result = dict(result)
            prov = dict(result.get("provenance", {}))
            prov["cached"] = True
            result["provenance"] = prov
            self._log_turn(
                parsed.intent, str(result.get("answer_mode", "quick")), True, False, "cache_hit", t0
            )
        return result, cached_before

    async def _execute_tools_and_llm(
        self,
        *,
        message: str,
        parsed: ParsedMessage,
        recent_turns: list[str],
        lat: float,
        lon: float,
        scale: Scale,
        sensitive: list[SensitiveGroup],
        context: dict[str, Any],
        reporter_hash: str,
        is_demo: bool,
        ref_now: datetime,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        bundle = FactsBundle(emergency_number="112")
        cards, early_clarify = await self._run_intent_tools(
            parsed,
            lat=lat,
            lon=lon,
            scale=scale,
            sensitive=sensitive,
            context=context,
            is_demo=is_demo,
            bundle=bundle,
        )
        if early_clarify is not None:
            return early_clarify

        resolved_ctx: dict[str, Any] = {
            "intent": parsed.intent.value,
            "lat": round(lat, 3),
            "lon": round(lon, 3),
            "scale": scale.value,
            "departure_time": parsed.departure_time.isoformat() if parsed.departure_time else None,
            "duration_min": parsed.duration_min,
            "mode": parsed.mode.value if parsed.mode else None,
            "activity": parsed.activity,
        }

        chips: list[dict[str, Any]] = []
        for hint in parsed.sensitive_hints:
            if hint not in sensitive:
                chips.append(
                    {
                        "label": f"Turn on cautious mode for {hint.value}?",
                        "action": "enable_sensitive",
                        "value": hint.value,
                    }
                )

        facts_json = build_facts_json(bundle)
        reports_block = build_user_reports_block(bundle.user_reports)
        allowed_nums = extract_allowed_numbers(facts_json)

        answer_mode = "quick"
        reason_code: str | None = None
        reply: dict[str, Any]
        ai_used = False

        can_ai, quota_reason = await self.quota.can_use_ai(reporter_hash, now=ref_now)
        if can_ai:
            user_content = build_user_content(
                message=message,
                recent_turns=recent_turns,
                resolved_context=resolved_ctx,
                facts_json=facts_json,
                user_reports=reports_block,
            )
            await self.quota.record_ai_call(reporter_hash, now=ref_now)
            ai_used = True
            draft, err_code = await self.gemini_client.generate(user_content)
            if draft is not None:
                is_valid, val_err = validate_draft(
                    draft,
                    allowed_numbers=allowed_nums,
                    valid_fact_ids=bundle.valid_ids(),
                )
                if is_valid:
                    answer_mode = "ai"
                    reply = {
                        "summary": draft.summary,
                        "recommendation": draft.recommendation,
                        "reasons": draft.reasons,
                        "caveats": draft.caveats,
                    }
                else:
                    reason_code = val_err
                    reply = build_quick_reply(parsed.intent, cards=cards, warnings=bundle.warnings)
            else:
                reason_code = err_code
                reply = build_quick_reply(parsed.intent, cards=cards, warnings=bundle.warnings)
        else:
            reason_code = quota_reason
            reply = build_quick_reply(parsed.intent, cards=cards, warnings=bundle.warnings)

        self._log_turn(parsed.intent, answer_mode, False, ai_used, reason_code, t0)
        return {
            "reply": reply,
            "answer_mode": answer_mode,
            "cards": cards,
            "chips": chips,
            "resolved_context": resolved_ctx,
            "provenance": {
                "source": "Delhi sample data" if is_demo else "BreatheMap + Open-Meteo",
                "is_demo": is_demo,
                "cached": False,
                "reason_code": reason_code,
            },
        }

    @staticmethod
    def _log_turn(
        intent: Intent,
        answer_mode: str,
        cache_hit: bool,
        ai_used: bool,
        reason_code: str | None,
        t0: float,
    ) -> None:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(
            "assistant_turn",
            extra={
                "intent": intent.value,
                "answer_mode": answer_mode,
                "cache_hit": cache_hit,
                "ai_used": ai_used,
                "reason_code": reason_code,
                "latency_ms": latency_ms,
            },
        )
