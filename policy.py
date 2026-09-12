"""Decision engine — SPEC §2, §6.2.

Consumes ``Venue`` + ``list[Candidate]``, returns a ``Decision``. Nothing
in this module knows about Slack, HTTP, CopilotKit, or component names —
that mapping is `policy_api.py`'s job, a later increment. This file only
ever sees the three contracts in `contracts.py`.

PROVIDER NOTE — deviates from SPEC §3/§6.2, which name the OpenAI SDK.
Switched to Gemini (free tier) on explicit instruction, not a silent
substitution. Structured output uses ``google-genai``'s
``client.models.generate_content(model=..., contents=..., config=
types.GenerateContentConfig(system_instruction=..., response_mime_type=
"application/json", response_schema=Decision))`` — confirmed against the
installed SDK (google-genai==2.23.0) via ``inspect.signature`` on
``generate_content`` and the ``model_fields`` of ``GenerateContentConfig``
/ ``GenerateContentResponse`` before writing this. The parsed result
lands at ``response.parsed`` (a ``Decision`` instance, per that field's
own description: "First candidate from the parsed response if
response_schema is provided"). Model id (``gemini-2.5-flash``) confirmed
against ``client.models.list()`` for this key rather than assumed.

Client and model are a single shared definition in `config.py` (P3's
`eval/` must hit the exact same one) — `get_client()` there is lazy, so
importing this module still never requires `GEMINI_API_KEY`. A caller
may still inject a `client` (tests do) to bypass both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from context_window.config import DEFAULT_MODEL, get_client
from context_window.contracts import Candidate, Decision, Venue

if TYPE_CHECKING:
    from google import genai

SOFT_GATE_SYSTEM_PROMPT = (
    "You decide whether it is appropriate to answer a question in a "
    "specific venue, given retrieved messages that everyone in that "
    "venue is already permitted to see. You are not checking access — "
    "that has already been verified. You are judging norms the access "
    "check cannot see: confidentiality markers, stated or implied "
    "purpose, and sensitivity of what is being discussed (e.g. a "
    "personnel change the subject hasn't been told about yet), even "
    "when nothing is explicitly marked confidential. If disclosing this "
    "could cause real harm before the people it's about have been told, "
    "or if it was said in a way that implies it should hold for now, "
    "prefer action='broker' with broker_owner_id set to that candidate's "
    "author, over action='allow'. "
    "`reason` must be ONE sentence, maximum 20 words, written to be read "
    "aloud to the person who asked — not a paragraph, not a justification."
)

#: SPEC §4: "reason ... shown to the user verbatim". A paragraph is
#: unreadable in a Slack card and on camera. This is the hard floor under
#: the prompt instruction above — it catches the model when it ignores
#: the instruction, so a paragraph can never actually reach the screen.
_MAX_REASON_CHARS = 140


def _one_line(reason: str) -> str:
    """Truncate at the last full word within `_MAX_REASON_CHARS`. Never
    appends anything — no ellipsis, no marker. Pure Python, no model."""
    if len(reason) <= _MAX_REASON_CHARS:
        return reason
    truncated = reason[:_MAX_REASON_CHARS]
    last_space = truncated.rfind(" ")
    return (truncated[:last_space] if last_space > 0 else truncated).rstrip()


def hard_gate(candidate: Candidate, venue: Venue) -> bool:
    """True = safe to say here. Pure Python. No model.

    If the people who can see the answer are not a subset of the people
    who could see the source, we are about to leak. This runs before any
    model call — a candidate that fails here never reaches the LLM, so no
    prompt can talk the system into leaking it.
    """
    return venue.audience <= candidate.source_audience


def decide(
    question: str,
    venue: Venue,
    candidates: list[Candidate],
    *,
    client: genai.Client | None = None,
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
       the model returned. This mechanical downgrade only fires on the
       explicit marker — SPEC's fourth fixture (no marker, norm still
       says hold) has nothing to catch it here. That case survives only
       if the model itself judges it, which is the whole point of that
       fixture.
    """
    survivors = [c for c in candidates if hard_gate(c, venue)]
    blocked = [c for c in candidates if not hard_gate(c, venue)]
    blocked_ids = [c.message_id for c in blocked]

    if not survivors:
        owner = blocked[0].author_id if blocked else None
        decision = Decision(
            action="broker",
            broker_owner_id=owner,
            reason=(
                f"Asking {owner.capitalize()}, who said it first."
                if owner
                else "No information found for this audience."
            ),
            blocked_candidate_ids=blocked_ids,
        )
        decision.reason = _one_line(decision.reason)
        return decision

    decision = _soft_gate(question, venue, survivors, client=client)
    decision.blocked_candidate_ids = blocked_ids

    if decision.action == "allow" and not decision.answer:
        # Deterministic fallback — never a second model call, never a
        # silent no-op on stage. Top surviving candidate's own text.
        decision.answer = survivors[0].text

    marked = next((c for c in survivors if c.confidential_marker), None)
    if marked is not None and decision.action == "allow":
        decision = Decision(
            action="broker",
            broker_owner_id=marked.author_id,
            reason=f"{marked.author_id.capitalize()} marked this confidential — asking first.",
            blocked_candidate_ids=blocked_ids,
        )

    decision.reason = _one_line(decision.reason)
    return decision


def _soft_gate(
    question: str,
    venue: Venue,
    survivors: list[Candidate],
    *,
    client: genai.Client | None = None,
) -> Decision:
    """One structured LLM call over candidates that already passed the
    hard gate. Judges norms the set maths can't see: confidentiality
    markers, purpose, sensitivity. SPEC §2, §6.2 step 3.
    """
    using_default_client = client is None
    if client is None:
        client = get_client()

    candidate_lines = "\n".join(
        f"- (id={c.message_id}, author={c.author_id}, "
        f"confidential_marker={c.confidential_marker}): {c.text}"
        for c in survivors
    )
    user_prompt = (
        f"Question: {question}\n"
        f"Venue: {venue.channel_name} ({'DM' if venue.is_dm else 'channel'}, "
        f"{len(venue.audience)} people can see the reply)\n"
        f"Candidates, already verified as visible to everyone in this venue:\n"
        f"{candidate_lines}"
    )

    # The SDK is only necessary when actually talking to Gemini.  Keeping it
    # out of the injected-client path lets deterministic policy tests run
    # without network/provider dependencies.
    if using_default_client:
        from google.genai import types as _genai_types

        generation_config: object = _genai_types.GenerateContentConfig(
            system_instruction=SOFT_GATE_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=Decision,
        )
    else:
        generation_config = None

    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=user_prompt,
        config=generation_config,
    )
    parsed = response.parsed
    if not isinstance(parsed, Decision):
        # Model declined to produce a parseable Decision — fail closed.
        return Decision(
            action="broker",
            broker_owner_id=survivors[0].author_id,
            reason="Could not confidently judge this one. Asking first.",
        )
    return parsed
