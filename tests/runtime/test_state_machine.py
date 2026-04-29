from app.runtime.state_machine import (
    CommandName,
    JobState,
    decide_command,
    decide_transition,
)


def test_allowed_transition_is_explicit() -> None:
    accepted = decide_transition(JobState.QUEUED, JobState.SCANNING)
    rejected = decide_transition(JobState.QUEUED, JobState.COMPLETED)

    assert accepted.accepted is True
    assert rejected.accepted is False


def test_command_targets_are_deterministic() -> None:
    pause = decide_command(JobState.COPYING, CommandName.PAUSE)
    resume = decide_command(JobState.COPYING, CommandName.RESUME)
    retry = decide_command(JobState.FAILED, CommandName.RETRY)
    refresh = decide_command(JobState.COMPLETED, CommandName.REFRESH)

    assert pause.accepted is True
    assert pause.state_after is JobState.PAUSING
    assert resume.accepted is False
    assert resume.state_after is JobState.COPYING
    assert retry.accepted is True
    assert retry.state_after is JobState.QUEUED
    assert refresh.accepted is True
    assert refresh.state_after is JobState.COMPLETED
