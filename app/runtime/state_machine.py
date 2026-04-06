from __future__ import annotations

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


class JobCommand(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY = "retry"


ACTIVE_STATES = {
    JobState.SCANNING,
    JobState.PREPARING,
    JobState.COPYING,
    JobState.PAUSING,
    JobState.VERIFYING,
    JobState.PARSING,
    JobState.CAPTURING,
    JobState.REPORTING,
}

RECOVERABLE_STATES = {
    JobState.QUEUED,
    JobState.PAUSED,
    JobState.WARN,
    JobState.FAILED,
}

TERMINAL_STATES = {
    JobState.WARN,
    JobState.FAILED,
    JobState.CANCELLED,
    JobState.COMPLETED,
}

ALLOWED_TRANSITIONS = {
    JobState.QUEUED: {JobState.SCANNING, JobState.CANCELLED},
    JobState.SCANNING: {JobState.PREPARING, JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.PREPARING: {JobState.COPYING, JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.COPYING: {JobState.PAUSING, JobState.VERIFYING, JobState.FAILED, JobState.CANCELLED},
    JobState.PAUSING: {JobState.PAUSED, JobState.FAILED},
    JobState.PAUSED: {JobState.COPYING, JobState.CANCELLED},
    JobState.VERIFYING: {JobState.PARSING, JobState.FAILED, JobState.CANCELLED, JobState.WARN},
    JobState.PARSING: {JobState.CAPTURING, JobState.FAILED, JobState.CANCELLED, JobState.WARN},
    JobState.CAPTURING: {JobState.REPORTING, JobState.FAILED, JobState.CANCELLED, JobState.WARN},
    JobState.REPORTING: {JobState.COMPLETED, JobState.WARN, JobState.FAILED, JobState.CANCELLED},
    JobState.WARN: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
    JobState.COMPLETED: set(),
}


def validate_transition(current: JobState, target: JobState) -> tuple[bool, str]:
    if target in ALLOWED_TRANSITIONS[current]:
        return True, ""
    return False, f"Transition {current.value} -> {target.value} is not allowed"


def command_allowed(state: JobState, command: JobCommand) -> tuple[bool, str]:
    if command is JobCommand.CANCEL and state in (
        JobState.QUEUED,
        JobState.SCANNING,
        JobState.PREPARING,
        JobState.COPYING,
        JobState.PAUSED,
        JobState.VERIFYING,
        JobState.PARSING,
        JobState.CAPTURING,
        JobState.REPORTING,
    ):
        return True, ""
    if command is JobCommand.PAUSE and state is JobState.COPYING:
        return True, ""
    if command is JobCommand.RESUME and state is JobState.PAUSED:
        return True, ""
    if command is JobCommand.RETRY and state in TERMINAL_STATES:
        return True, ""
    return False, f"Command {command.value} is not allowed in state {state.value}"
