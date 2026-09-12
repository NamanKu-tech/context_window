"""Confidentiality markers — SPEC §4 note, §6.1.

Which phrases count as "keep this quiet" is a policy judgement, not a
storage concern, so it lives here under P1, not in store.py.

``store.py`` calls ``has_confidential_marker`` at ingest to set
``Candidate.confidential_marker``. ``seed/workspace.py`` does **not** set
the flag itself — it only writes message text containing these phrases;
whoever ingests the fixture data is responsible for running it through
this check.

Plain substring matching. No model — SPEC §6.1 is explicit that this must
be deterministic and auditable.
"""

from __future__ import annotations

CONFIDENTIAL_MARKERS: tuple[str, ...] = (
    "between us",
    "between you and me",
    "confidential",
    "don't share",
    "dont share",
    "do not share",
    "don't spread",
    "dont spread",
    "don't repeat",
    "dont repeat",
    "keep this quiet",
    "keep this to yourself",
    "keep it in here",
    "keep this in here",
    "keep this between",
    "not for sharing",
    "off the record",
    "please hold it here",
    "hold this for now",
)


def has_confidential_marker(text: str) -> bool:
    """True if ``text`` carries one of the confidentiality phrases.

    Deliberately dumb: lowercase substring containment, no model, no regex
    cleverness. If it misses a phrase, add the phrase.
    """
    lowered = text.lower()
    return any(marker in lowered for marker in CONFIDENTIAL_MARKERS)


__all__ = ["CONFIDENTIAL_MARKERS", "has_confidential_marker"]
