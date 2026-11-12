"""Stubbed checks that onboarding prompts encode open-question rules."""

from app.agents.onboarding import GOALS_SYSTEM_PROMPT, SYSTEM_PROMPT


def test_profile_prompt_avoids_yes_no_detail_loops():
    text = " ".join(SYSTEM_PROMPT.lower().split())
    assert "what, how, or which" in text
    assert "never ask a yes/no question when you need details" in text
    assert "rephrase into one concrete question" in text
    assert "do not repeat the same ask" in text
    assert "skip" in text


def test_goals_prompt_still_present():
    assert "preparation coach" in GOALS_SYSTEM_PROMPT.lower() or "goals" in GOALS_SYSTEM_PROMPT.lower()
