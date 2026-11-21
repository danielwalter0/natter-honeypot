"""apply_extraction changes nothing when it fails part-way."""

from types import SimpleNamespace
from typing import Any

import pytest

from natter import session
from natter.check import Rejection
from natter.schema import Dossier, Stage
from natter.session import SessionState, add_scammer_line, apply_extraction


def test_failed_stage_step_leaves_state_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    state = SessionState(previous_stage=Stage.HOOK)
    add_scammer_line(state, "hello there")
    old_dossier = state.dossier
    # A "checked" dossier whose stage has no .value, plus one drop: the stage step must raise
    no_value: Any = SimpleNamespace()  # typed Any so mypy lets it stand in for a stage
    odd = Dossier.model_construct(stage=no_value)
    monkeypatch.setattr(session, "check_dossier", lambda p, t, s: (odd, [Rejection("x", "y")]))
    with pytest.raises(AttributeError):
        apply_extraction(state, Dossier())
    assert state.dossier is old_dossier
    assert state.rejections == [] and state.rejection_turns == []
    assert state.previous_stage == Stage.HOOK
