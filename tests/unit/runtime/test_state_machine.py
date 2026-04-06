from __future__ import annotations

import unittest

from app.runtime.state_machine import JobCommand, JobState, command_allowed, validate_transition


class JobStateMachineTests(unittest.TestCase):
    def test_happy_path_transition_allowed(self) -> None:
        allowed, reason = validate_transition(JobState.QUEUED, JobState.SCANNING)
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_invalid_transition_rejected(self) -> None:
        allowed, reason = validate_transition(JobState.QUEUED, JobState.COMPLETED)
        self.assertFalse(allowed)
        self.assertIn("not allowed", reason)

    def test_pause_only_allowed_while_copying(self) -> None:
        allowed, _ = command_allowed(JobState.COPYING, JobCommand.PAUSE)
        self.assertTrue(allowed)
        allowed, _ = command_allowed(JobState.QUEUED, JobCommand.PAUSE)
        self.assertFalse(allowed)

    def test_retry_only_allowed_from_terminal_states(self) -> None:
        for state in (JobState.WARN, JobState.FAILED, JobState.CANCELLED, JobState.COMPLETED):
            allowed, _ = command_allowed(state, JobCommand.RETRY)
            self.assertTrue(allowed)
        allowed, _ = command_allowed(JobState.QUEUED, JobCommand.RETRY)
        self.assertFalse(allowed)
