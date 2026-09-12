"""FastAPI boundary — SPEC §4b. One route: POST /decide.

Glue, not logic. Resolves a Venue + Candidates, calls `policy.decide`,
maps the typed `Decision` onto a component name + JSON-serializable
props. No gate logic lives here — that's all in `policy.py`, which stays
free of HTTP, Slack and component names.

Prop contract — conforms to `channel/components.tsx`'s actual declared
types (source of truth, read directly, not re-derived): P1 conforms to
P3, not the other way round.

    DisclosureDecisionProps = { action, reason, answer?, redactedAnswer?, audience? }
    AudienceCardProps       = { sourceAudience, venueAudience, ownerName, status }

`DisclosureDecision` is the *only* component this endpoint ever names —
TSX already handles all three actions itself and nests `AudienceCard`
internally (`props.audience`) when `action === "broker"`. Sending
`"AudienceCard"` directly, as an earlier version of this file did,
bypassed that nesting and TSX's "Permission needed" header/redact body
entirely. `audience` is populated only for `broker`/`redact`; omitted
(`None`) on `allow`, matching the optional `audience?` field.

Venue.audience / Candidate.source_audience are `set[str]` — not
JSON-serializable and not renderable ("dana" has no avatar). Both are
resolved through `resolve_users` into `{id, name, avatarUrl}` lists at
this boundary.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from context_window.contracts import Candidate, Decision, Venue
from context_window.policy import decide, hard_gate

try:
    from context_window.store import build_venue, search  # P2's module
except ImportError:
    build_venue = None
    search = None

app = FastAPI()


class DecideRequest(BaseModel):
    channel_id: str
    user_id: str
    text: str
    thread_ts: str
    acting_for: str | None = None


class DecideResponse(BaseModel):
    action: Literal["allow", "redact", "broker"]
    reason: str
    component: Literal["DisclosureDecision"]
    props: dict[str, Any]


def resolve_users(ids: set[str] | list[str]) -> list[dict[str, str]]:
    """user id -> [{id, name, avatarUrl}, ...], sorted by id.

    `avatarUrl` is `""`, not `None` — TSX's `AudienceMember.avatarUrl` is
    a required `string`, and `<Image src={null}>` is a live render
    failure, not just a type complaint. An empty string is a valid
    string and the safer stand-in until real avatar URLs exist.

    STUB seam: this body is the only thing P2 needs to replace on
    integration — swap it for a lookup backed by (cached) `users_info`
    and keep this exact signature/return shape. Nothing else in this
    file, or in either component, changes.
    """
    return [{"id": uid, "name": uid.capitalize(), "avatarUrl": ""} for uid in sorted(ids)]


# STUB — owned by P2, delete on integration. Fixed cast + channels from
# SPEC §6.6, and the three fixtures from §6.2/§6.7 as the only content.
# `search` here is keyword matching, not real retrieval — store.search
# will replace this wholesale once it exists.
_STUB_CHANNELS: dict[str, Venue] = {
    "general": Venue("general", "#general", False, {"dana", "sam", "rahul", "priya"}),
    "engineering": Venue("engineering", "#engineering", False, {"dana", "rahul", "priya"}),
    "leadership": Venue("leadership", "#leadership", False, {"dana", "sam"}),
    "hiring": Venue("hiring", "#hiring", False, {"dana", "sam"}),
    "dm_dana_sam": Venue("dm_dana_sam", "DM: Dana, Sam", True, {"dana", "sam"}),
}

_STUB_CANDIDATES: list[Candidate] = [
    Candidate(
        message_id="m1",
        text="new senior-eng salary band is 180-210k",
        author_id="sam",
        source_channel_id="leadership",
        source_audience={"dana", "sam"},
        confidential_marker=False,
    ),
    Candidate(
        message_id="m2",
        text="deploy went out fine, lunch is at noon",
        author_id="rahul",
        source_channel_id="general",
        source_audience={"dana", "sam", "rahul", "priya"},
        confidential_marker=False,
    ),
    Candidate(
        message_id="m4",
        text=(
            "We're moving Priya to the platform team next quarter — "
            "still figuring out how to tell her."
        ),
        author_id="sam",
        source_channel_id="leadership",
        source_audience={"dana", "sam"},
        confidential_marker=False,
    ),
]


def _stub_venue_and_candidates(req: DecideRequest) -> tuple[Venue, list[Candidate]]:
    # STUB — owned by P2, delete on integration
    venue = _STUB_CHANNELS.get(
        req.channel_id, Venue(req.channel_id, req.channel_id, False, set()),
    )
    text = req.text.lower()
    if "salary" in text or "band" in text:
        candidates = [_STUB_CANDIDATES[0]]
    elif "deploy" in text:
        candidates = [_STUB_CANDIDATES[1]]
    elif "priya" in text:
        candidates = [_STUB_CANDIDATES[2]]
    else:
        candidates = list(_STUB_CANDIDATES)
    return venue, candidates


def _resolve(req: DecideRequest) -> tuple[Venue, list[Candidate]]:
    if build_venue is not None and search is not None:
        # Real path, once P2 ships store.py + slack_client.py. Not
        # exercised until then.
        from context_window.slack_client import get_client as get_slack_client

        venue = build_venue(get_slack_client(), req.channel_id)
        candidates = search(req.text)
        return venue, candidates
    return _stub_venue_and_candidates(req)


def _source_candidate(
    decision: Decision, venue: Venue, candidates: list[Candidate]
) -> Candidate | None:
    """Which candidate `sourceAudience` describes.

    broker/redact: the held candidate (matched by `broker_owner_id`) —
    it may be a *blocked* candidate (fixture 1: hard gate failed, so it
    never made it into `survivors`), which is why this searches the full
    candidate list, not just survivors.

    allow: no `broker_owner_id` to key off, so the top surviving
    candidate — the one the answer actually came from.
    """
    if decision.broker_owner_id:
        held = next((c for c in candidates if c.author_id == decision.broker_owner_id), None)
        if held is not None:
            return held
    survivors = [c for c in candidates if hard_gate(c, venue)]
    return survivors[0] if survivors else None


def _to_response(
    decision: Decision, venue: Venue, candidates: list[Candidate]
) -> DecideResponse:
    audience: dict[str, Any] | None = None
    if decision.action in ("broker", "redact"):
        source = _source_candidate(decision, venue, candidates)
        owner_id = decision.broker_owner_id or (source.author_id if source else None)
        audience = {
            "sourceAudience": resolve_users(source.source_audience if source else set()),
            "venueAudience": resolve_users(venue.audience),
            "ownerName": resolve_users([owner_id])[0]["name"] if owner_id else "",
            "status": decision.action,  # "broker" | "redact"
        }

    props: dict[str, Any] = {
        "action": decision.action,
        "reason": decision.reason,
        "answer": decision.answer,
        "redactedAnswer": decision.redacted_answer,
        "audience": audience,
    }

    return DecideResponse(
        action=decision.action,
        reason=decision.reason,
        component="DisclosureDecision",
        props=props,
    )


@app.post("/decide")
def post_decide(req: DecideRequest) -> DecideResponse:
    venue, candidates = _resolve(req)
    decision = decide(req.text, venue, candidates)
    return _to_response(decision, venue, candidates)
