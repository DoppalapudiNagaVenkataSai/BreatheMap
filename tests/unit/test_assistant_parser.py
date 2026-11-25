"""Unit tests for assistant rule-based parser, safety detection, and precedence (40+ phrases)."""

from datetime import UTC, datetime

import pytest

from app.assistant.intents import Intent
from app.assistant.parser import parse_message
from app.domain.models import Mode, SensitiveGroup

NOW = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)  # 15:30 IST


@pytest.mark.parametrize(
    ("phrase", "expected_intent"),
    [
        ("Hi", Intent.GREETING),
        ("Hello!", Intent.GREETING),
        ("What can you do?", Intent.GREETING),
        ("I can't breathe right now", Intent.EMERGENCY),
        ("Having chest pain and shortness of breath", Intent.EMERGENCY),
        ("My friend is having an asthma attack", Intent.EMERGENCY),
        ("Should I take my inhaler before going out?", Intent.MEDICAL),
        ("What medication should you prescribe for cough?", Intent.MEDICAL),
        ("Can you diagnose my breathing issue?", Intent.MEDICAL),
        ("What is the bitcoin price today?", Intent.OUT_OF_SCOPE),
        ("Give me a biryani recipe", Intent.OUT_OF_SCOPE),
        ("Write a python script to scrape a site", Intent.OUT_OF_SCOPE),
        ("How's the air near me?", Intent.AIR_NOW),
        ("What is the current AQI?", Intent.AIR_NOW),
        ("Check pollution level right now", Intent.AIR_NOW),
        ("When's the cleanest time to go out today?", Intent.BEST_TIME),
        ("What is the best time to go out?", Intent.BEST_TIME),
        ("When is the worst time for smog?", Intent.BEST_TIME),
        ("Can I jog at 6 PM for 40 min?", Intent.ACTIVITY_ADVICE),
        ("Is it okay to run for 30 minutes this evening?", Intent.ACTIVITY_ADVICE),
        ("Can I do yoga outdoors at 7 am for an hour?", Intent.ACTIVITY_ADVICE),
        ("My kids want to play outside for 45 min now", Intent.ACTIVITY_ADVICE),
        ("Going to New Delhi Railway Station at 10 PM, best way?", Intent.ROUTE_COMPARE),
        ("Best way from Connaught Place to India Gate now", Intent.ROUTE_COMPARE),
        ("How should I commute to Hauz Khas by metro?", Intent.ROUTE_COMPARE),
        ("Compare routes to ITO at 18:00", Intent.ROUTE_COMPARE),
        ("How do I keep the air cleaner at home?", Intent.HOME_TIPS),
        ("Should I open windows in my room?", Intent.HOME_TIPS),
        ("Tips for indoor kitchen smoke and purifier", Intent.HOME_TIPS),
        ("Any smoke reported near me?", Intent.REPORTS_NEARBY),
        ("Are there community reports near here?", Intent.REPORTS_NEARBY),
        ("Any open burning reported nearby?", Intent.REPORTS_NEARBY),
        ("I see garbage burning, how do I report it?", Intent.REPORT_HELP),
        ("Where to report construction dust?", Intent.REPORT_HELP),
        ("What is PM2.5?", Intent.EXPLAIN),
        ("What does NAQI mean?", Intent.EXPLAIN),
        ("Explain winter inversion", Intent.EXPLAIN),
        ("Define inhalation rate", Intent.EXPLAIN),
        ("Can I cycle for half an hour at 5 pm?", Intent.ACTIVITY_ADVICE),
        ("Going to reach Anand Vihar in 2 hours by auto", Intent.ROUTE_COMPARE),
    ],
)
def test_parser_intent_classification_40_phrases(phrase: str, expected_intent: Intent) -> None:
    parsed = parse_message(phrase, now=NOW)
    assert parsed.intent == expected_intent


def test_parser_times_durations_modes_places_and_precedence() -> None:
    p1 = parse_message("Going from CP to India Gate at 10 PM by metro for 1.5 hrs", now=NOW)
    assert p1.origin_text == "CP"
    assert p1.destination_text == "India Gate"
    assert p1.mode == Mode.METRO
    assert p1.duration_min == 90
    assert p1.departure_time is not None
    assert p1.departure_time.hour == 22

    p2 = parse_message("Can I jog tomorrow 7am for half an hour with my child?", now=NOW)
    assert p2.activity == "jog"
    assert p2.duration_min == 30
    assert p2.departure_time is not None
    assert p2.departure_time.hour == 7
    assert SensitiveGroup.CHILD in p2.sensitive_hints

    # Message values win over UI context
    p3 = parse_message(
        "Going to India Gate at 22:00 by metro",
        context={"mode": "car", "activity": "jog"},
        now=NOW,
    )
    assert p3.mode == Mode.METRO
    assert p3.activity == "jog"
