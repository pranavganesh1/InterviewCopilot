from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TurnEvaluation(BaseModel):
    coverage: Literal["none", "partial", "good", "excellent"]
    strengths: list[str] = []
    gaps: list[str] = []
    expected_answer_explanation: str = ""
    corrected_code: str = ""
    time_complexity: str = ""
    space_complexity: str = ""


class AssistanceEvent(BaseModel):
    assistance_event_id: str
    level: int
    assistance_type: str
    content: str
    created_at: str


class TurnOut(BaseModel):
    """Turn as returned by the interview session API (no answer redaction needed)."""

    turn_index: int
    question_area: str
    question: str
    question_type: str | None = None
    # optional question-type-specific fields
    options: list[str] = []
    code_snippet: str = ""
    objective: str = ""
    scenario: str = ""
    unit: str = ""
    # full turn fields (present in get_session, absent in start_session)
    answer: str | None = None
    assisted: bool = False
    assistance_level: int = 0
    assistance_events: list[AssistanceEvent] = []
    evaluation: TurnEvaluation | None = None

    model_config = {"extra": "allow"}  # public_question_meta may add future fields


class SessionOut(BaseModel):
    id: str
    track_id: str | None = None  # absent in open-session shape
    mode: str
    status: str
    max_turns: int
    duration_minutes: int
    created_at: str | None = None
    # open-session-only fields
    question_index: int | None = None
    answered_count: int | None = None
    # start-session-only fields
    practice_label: str | None = None
    persona_id: str | None = None
    persona_name: str | None = None


class SessionWithTurn(BaseModel):
    """Response for POST /tracks/{track_id}/sessions."""

    session: SessionOut
    turn: TurnOut


class SessionWithTurns(BaseModel):
    """Response for GET /sessions/{session_id}."""

    session: SessionOut
    turns: list[TurnOut]


class OpenSessionResult(BaseModel):
    """Response for GET /tracks/{track_id}/open-session."""

    session: SessionOut | None
    # Additive: all open sessions on the track, newest first.
    sessions: list[SessionOut] = []


class OpenSessionRow(BaseModel):
    """One unfinished interview for GET /me/open-sessions."""

    session_id: str
    track_id: str
    track_subject: str
    mode: str
    status: str
    question_index: int
    max_turns: int
    answered_count: int
    created_at: str | None = None
    duration_minutes: int = 60


class CloseEmptyResult(BaseModel):
    """Response for POST /tracks/{track_id}/close-empty-sessions."""

    closed_count: int
    session_ids: list[str] = []


class TurnResult(BaseModel):
    """Response for POST /sessions/{session_id}/turns."""

    completed: bool
    evaluation: TurnEvaluation
    turn: TurnOut | None = None
