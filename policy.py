"""Decision engine — SPEC §2, §6.2.

This increment: hard_gate() only. No soft gate, no LLM call, no import
from openai. decide() and the soft gate land in the next increment.
"""

from __future__ import annotations

from context_window.types import Candidate, Venue


def hard_gate(candidate: Candidate, venue: Venue) -> bool:
    """True = safe to say here. Pure Python. No model.

    If the people who can see the answer are not a subset of the people
    who could see the source, we are about to leak. This runs before any
    model call — a candidate that fails here never reaches the LLM, so no
    prompt can talk the system into leaking it.
    """
    return venue.audience <= candidate.source_audience
