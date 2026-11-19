"""Seen / Reported state machine of one problem (spec §4.4)."""

from __future__ import annotations

from dataclasses import dataclass

from ..model.problems import Problem

SEEN = "Seen"
REPORTED = "Reported"


@dataclass
class ProblemLifecycle:
    """One machine per problem `p`, created on X=>M_up(p), removed when it ends."""

    problem: Problem
    since: str
    state: str = SEEN

    @property
    def timer(self) -> str:
        """Name of its delay timer (M_delay_timeout)."""
        return f"delay:{self.problem.key}"
