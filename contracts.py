"""Frozen contracts — SPEC §4.

Everything in the project imports from this module. Field names here are
frozen: three people code against them in parallel. Do not add fields, do
not rename anything without saying so loudly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass
class Venue:
    """Where the question was asked."""

    channel_id: str
    channel_name: str
    is_dm: bool
    audience: set[str]  # user ids who can see the reply


@dataclass
class Candidate:
    """One retrieved message."""

    message_id: str
    text: str
    author_id: str  # the person we would have to ask
    source_channel_id: str
    source_audience: set[str]  # user ids who could see the original
    confidential_marker: bool  # "between us", "don't share", "confidential", "keep this quiet"


class Decision(BaseModel):
    """The only thing policy returns."""

    action: Literal["allow", "redact", "broker"]
    answer: str | None = None
    redacted_answer: str | None = None
    broker_owner_id: str | None = None
    reason: str  # one line, shown to the user verbatim
    blocked_candidate_ids: list[str] = []
