from __future__ import annotations

from datetime import timezone

import pytest


from src.agent.prompts import format_prompt
from src.agent.state import AgentState, StateManager


@pytest.fixture(autouse=True)
def _reset_state_manager() -> None:
    StateManager._memory_store.clear()  # type: ignore[attr-defined]
    yield
    StateManager._memory_store.clear()  # type: ignore[attr-defined]


def _sample_state(session_id: str = "session-1", status: str = "initialized") -> AgentState:
    return AgentState(
        session_id=session_id,
        report_id="report-123",
        report_text="Extensive report text describing pulmonary nodules and follow-up.",
        status=status,  # type: ignore[arg-type]
    )


def test_agent_state_serialisation_round_trip_preserves_data() -> None:
    state = _sample_state()
    state.add_finding({"finding_id": "f1", "type": "nodule", "size_mm": 6})
    state.add_guideline({"source": "Fleischner 2017"})
    state.add_recommendation({"follow_up_type": "CT", "urgency": "urgent"})
    state.add_decision_step("parse_report", {"result": "success"})

    serialised = state.to_dict()
    assert isinstance(serialised["created_at"], str)
    assert isinstance(serialised["updated_at"], str)

    restored = AgentState.from_dict(serialised)
    assert restored.session_id == state.session_id
    assert restored.findings == state.findings
    assert restored.recommendations == state.recommendations
    assert restored.decision_trace[0]["step"] == "parse_report"
    assert restored.created_at.tzinfo == timezone.utc
    assert restored.updated_at >= restored.created_at


def test_state_manager_tracks_active_sessions_and_raises_for_missing() -> None:
    active = _sample_state("session-active", status="parsing")
    completed = _sample_state("session-done", status="completed")
    StateManager.save_state(active)
    StateManager.save_state(completed)

    assert StateManager.load_state("session-active") is active
    assert StateManager.list_active_sessions() == ["session-active"]

    StateManager.clear_state("session-active")
    with pytest.raises(KeyError):
        StateManager.load_state("unknown-session")


def test_format_prompt_populates_placeholders() -> None:
    prompt = format_prompt("Finding: {finding}; Action: {action}", finding="RUL nodule", action="follow-up")
    assert "RUL nodule" in prompt
    assert "follow-up" in prompt
