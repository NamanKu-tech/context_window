"""Decision engine — SPEC §2, §6.2.

Consumes ``Venue`` + ``list[Candidate]``, returns a ``Decision``. Nothing
in this module knows about Slack, HTTP, CopilotKit, or component names —
that mapping is `policy_api.py`'s job, a later increment. This file only
ever sees the three contracts in `contracts.py`.

Structured LLM calls use the OpenAI SDK's Pydantic parse helper,
``client.chat.completions.parse(model=..., messages=[...],
response_format=Decision)`` — confirmed against the installed SDK
(openai==3.13.0) via ``inspect.signature`` and the method's own docstring
before writing this. The result lands at
``completion.choices[0].message.parsed``. (``client.responses.parse``
also exists in this SDK version but ships with no docstring here and is
the newer, less-established path for this use case — going with
``chat.completions.parse`` since it is documented, stable, and is what
the spec calls "the Pydantic parse helper".)

The client is injected, not constructed at import time or module scope:
building ``openai.OpenAI()`` eagerly raises the moment ``OPENAI_API_KEY``
is unset, which would make this module unimportable without a key. It is
only ever constructed lazily, inside ``_soft_gate``, and only when a
candidate actually survives the hard gate.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol

from context_window.contracts import Candidate, Decision, Venue

if TYPE_CHECKING:
    from openai import OpenAI

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-2024-08-06")


def hard_gate(candidate: Candidate, venue: Venue) -> bool:
    """True = safe to say here. Pure Python. No model.

    If the people who can see the answer are not a subset of the people
    who could see the source, we are about to leak. This runs before any
    model call — a candidate that fails here never reaches the LLM, so no
    prompt can talk the system into leaking it.
    """
    return venue.audience <= candidate.source_audience


class _ChatCompletionsClient(Protocol):
    """The minimal shape `_soft_gate` needs from an OpenAI client.

    Lets tests inject a stub without importing/constructing the real
    `openai.OpenAI` client.
    """

    chat: object  # narrowed via duck typing at the call site


def decide(
    question: str,
    venue: Venue,
    candidates: list[Candidate],
    *,
    client: OpenAI | None = None,
) -> Decision:
    """SPEC §6.2, order of operations exactly as specified:

    1. Partition candidates with `hard_gate`. Failures are blocked before
       any model call — their ids go in `blocked_candidate_ids`.
    2. If nothing survives -> broker, owner = author of the most relevant
       blocked candidate (the first blocked candidate in `candidates`
       order — callers are expected to hand this function already
       ranked-by-relevance, e.g. from `store.search`).
    3. If something survives -> one structured LLM call over the
       survivors.
    4. Soft gate: still downgrade `allow` -> `broker` when a surviving
       candidate carries `confidential_marker=True`, regardless of what
       the model returned. This is the project's differentiator (SPEC
       §6.6 fact #3) — it must hold even if the model gets it wrong, so
       it is enforced here in code, not left to the model's judgment.
    """
    survivors = [c for c in candidates if hard_gate(c, venue)]
    blocked = [c for c in candidates if not hard_gate(c, venue)]
    blocked_ids = [c.message_id for c in blocked]

    if not survivors:
        owner = blocked[0].author_id if blocked else None
        return Decision(
            action="broker",
            broker_owner_id=owner,
            reason=(
                f"The only relevant information lives somewhere this audience "
                f"can't see. Asking {owner}, who said it first."
                if owner
                else "No information found for this audience."
            ),
            blocked_candidate_ids=blocked_ids,
        )

    decision = _soft_gate(question, venue, survivors, client=client)
    decision.blocked_candidate_ids = blocked_ids

    marked = next((c for c in survivors if c.confidential_marker), None)
    if marked is not None and decision.action == "allow":
        decision = Decision(
            action="broker",
            broker_owner_id=marked.author_id,
            reason=(
                f"{marked.author_id} marked this confidential. Holding it "
                f"until they say it's OK."
            ),
            blocked_candidate_ids=blocked_ids,
        )

    return decision


def _soft_gate(
    question: str,
    venue: Venue,
    survivors: list[Candidate],
    *,
    client: OpenAI | None = None,
) -> Decision:
    """One structured LLM call over candidates that already passed the
    hard gate. Judges norms the set maths can't see: confidentiality
    markers, purpose, sensitivity. SPEC §2, §6.2 step 3.
    """
    if client is None:
        from openai import OpenAI as _OpenAI

        client = _OpenAI()

    candidate_lines = "\n".join(
        f"- (id={c.message_id}, author={c.author_id}, "
        f"confidential_marker={c.confidential_marker}): {c.text}"
        for c in survivors
    )
    system_prompt = (
        "You decide whether it is appropriate to answer a question in a "
        "specific venue, given retrieved messages that everyone in that "
        "venue is already permitted to see. You are not checking access — "
        "that has already been verified. You are judging norms the access "
        "check cannot see: confidentiality markers, purpose, sensitivity. "
        "If any candidate carries a confidentiality marker, prefer "
        "action='broker' with broker_owner_id set to that candidate's "
        "author, over action='allow'."
    )
    user_prompt = (
        f"Question: {question}\n"
        f"Venue: {venue.channel_name} ({'DM' if venue.is_dm else 'channel'}, "
        f"{len(venue.audience)} people can see the reply)\n"
        f"Candidates, already verified as visible to everyone in this venue:\n"
        f"{candidate_lines}"
    )

    completion = client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=Decision,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        # Model declined to produce a parseable Decision — fail closed.
        return Decision(
            action="broker",
            broker_owner_id=survivors[0].author_id,
            reason="Could not confidently judge this one. Asking first.",
        )
    return parsed
