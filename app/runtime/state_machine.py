"""Runtime state and command foundations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "QUEUED"
    SCANNING = "SCANNING"
    PREPARING = "PREPARING"
    COPYING = "COPYING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    VERIFYING = "VERIFYING"
    PARSING = "PARSING"
    CAPTURING = "CAPTURING"
    REPORTING = "REPORTING"
    WARN = "WARN"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class CommandName(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY = "retry"
    REFRESH = "refresh"


TERMINAL_STATES = frozenset({JobState.CANCELLED, JobState.COMPLETED})
RECOVERABLE_STATES = frozenset({JobState.QUEUED, JobState.PAUSED, JobState.WARN, JobState.FAILED})

COMMAND_MATRIX: dict[JobState, frozenset[CommandName]] = {
    JobState.QUEUED: frozenset({CommandName.CANCEL, CommandName.REFRESH}),
    JobState.SCANNING: frozenset({CommandName.CANCEL, CommandName.REFRESH}),
    JobState.PREPARING: frozenset({CommandName.CANCEL, CommandName.REFRESH}),
    JobState.COPYING: frozenset({CommandName.PAUSE, CommandName.CANCEL, CommandName.REFRESH}),
    JobState.PAUSING: frozenset({CommandName.REFRESH}),
    JobState.PAUSED: frozenset({CommandName.RESUME, CommandName.CANCEL, CommandName.REFRESH}),
    JobState.VERIFYING: frozenset({CommandName.CANCEL, CommandName.REFRESH}),
    JobState.PARSING: frozenset({CommandName.CANCEL, CommandName.REFRESH}),
    JobState.CAPTURING: frozenset({CommandName.CANCEL, CommandName.REFRESH}),
    JobState.REPORTING: frozenset({CommandName.CANCEL, CommandName.REFRESH}),
    JobState.WARN: frozenset({CommandName.RETRY, CommandName.REFRESH}),
    JobState.FAILED: frozenset({CommandName.RETRY, CommandName.REFRESH}),
    JobState.CANCELLED: frozenset({CommandName.REFRESH}),
    JobState.COMPLETED: frozenset({CommandName.REFRESH}),
}


@dataclass(frozen=True)
class CommandDecision:
    command: CommandName
    state: JobState
    state_after: JobState
    accepted: bool
    reason: str


ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.SCANNING, JobState.FAILED, JobState.CANCELLED}),
    JobState.SCANNING: frozenset({JobState.PREPARING, JobState.FAILED, JobState.CANCELLED}),
    JobState.PREPARING: frozenset({JobState.COPYING, JobState.FAILED, JobState.CANCELLED}),
    JobState.COPYING: frozenset(
        {JobState.PAUSING, JobState.VERIFYING, JobState.WARN, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.PAUSING: frozenset({JobState.PAUSED, JobState.FAILED}),
    JobState.PAUSED: frozenset({JobState.COPYING, JobState.CANCELLED}),
    JobState.VERIFYING: frozenset(
        {JobState.PARSING, JobState.WARN, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.PARSING: frozenset(
        {JobState.CAPTURING, JobState.REPORTING, JobState.WARN, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.CAPTURING: frozenset(
        {JobState.REPORTING, JobState.WARN, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.REPORTING: frozenset(
        {JobState.COMPLETED, JobState.WARN, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.WARN: frozenset(
        {JobState.QUEUED, JobState.REPORTING, JobState.COMPLETED, JobState.FAILED}
    ),
    JobState.FAILED: frozenset({JobState.QUEUED}),
    JobState.CANCELLED: frozenset(),
    JobState.COMPLETED: frozenset(),
}

COMMAND_TARGETS: dict[CommandName, dict[JobState, JobState]] = {
    CommandName.PAUSE: {JobState.COPYING: JobState.PAUSING},
    CommandName.RESUME: {JobState.PAUSED: JobState.COPYING},
    CommandName.CANCEL: {
        state: JobState.CANCELLED
        for state in (
            JobState.QUEUED,
            JobState.SCANNING,
            JobState.PREPARING,
            JobState.COPYING,
            JobState.PAUSED,
            JobState.VERIFYING,
            JobState.PARSING,
            JobState.CAPTURING,
            JobState.REPORTING,
        )
    },
    CommandName.RETRY: {JobState.WARN: JobState.QUEUED, JobState.FAILED: JobState.QUEUED},
    CommandName.REFRESH: {state: state for state in JobState},
}


@dataclass(frozen=True)
class TransitionDecision:
    state_before: JobState
    state_after: JobState
    accepted: bool
    reason: str


def decide_transition(state_before: JobState, state_after: JobState) -> TransitionDecision:
    """Return whether a runtime transition is allowed."""

    if state_after in ALLOWED_TRANSITIONS[state_before]:
        return TransitionDecision(
            state_before=state_before,
            state_after=state_after,
            accepted=True,
            reason=f"{state_before.value} can transition to {state_after.value}",
        )
    return TransitionDecision(
        state_before=state_before,
        state_after=state_after,
        accepted=False,
        reason=f"{state_before.value} cannot transition to {state_after.value}",
    )


def decide_command(state: JobState, command: CommandName) -> CommandDecision:
    """Return a conservative command decision for the current state."""

    if command in COMMAND_MATRIX[state]:
        state_after = COMMAND_TARGETS[command][state]
        return CommandDecision(
            command=command,
            state=state,
            state_after=state_after,
            accepted=True,
            reason=f"{command.value} is allowed from {state.value}",
        )
    return CommandDecision(
        command=command,
        state=state,
        state_after=state,
        accepted=False,
        reason=f"{command.value} is not allowed from {state.value}",
    )
