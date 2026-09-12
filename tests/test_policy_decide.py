"""SPEC §6.2 acceptance test for policy.decide() — no Slack required.

Three fixtures, exactly as specified:
  1. fact from #leadership, asked in #general      -> broker (hard gate fails)
  2. fact from #general, asked in #general         -> allow
  3. confidential fact from #leadership, asked in a
     DM that is a subset of #leadership            -> broker (hard passes,
                                                       soft gate holds)

Fixture 3 is the project's differentiator (SPEC §6.6 fact #3). It is
tested here with a stub LLM client that (wrongly) returns "allow" for it,
to prove the soft-gate downgrade in `policy.decide` holds even when the
model gets it wrong — the safety property does not depend on the model
behaving.
"""

from context_window.contracts import Candidate, Decision, Venue
from context_window.policy import decide, _one_line


class _FakeResponse:
    def __init__(self, decision: Decision) -> None:
        self.parsed = decision


class _FakeModels:
    def __init__(self, decision: Decision) -> None:
        self._decision = decision
        self.calls = 0

    def generate_content(self, **_kwargs: object) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(self._decision)


class _FakeClient:
    """Stands in for `genai.Client()` — same `.models.generate_content()`
    shape, no network, no API key required."""

    def __init__(self, decision: Decision) -> None:
        self.models = _FakeModels(decision)


def test_fixture1_leadership_fact_asked_in_general_brokers() -> None:
    """Hard gate fails -> broker. No survivors, so no LLM call happens at
    all — decide() is called without a client to prove the model is never
    touched for a fully-blocked candidate set."""
    salary_band = Candidate(
        message_id="m1",
        text="new senior-eng salary band is 180-210k",
        author_id="sam",
        source_channel_id="leadership",
        source_audience={"dana", "sam"},
        confidential_marker=False,
    )
    general = Venue(
        channel_id="general",
        channel_name="#general",
        is_dm=False,
        audience={"dana", "sam", "rahul", "priya"},
    )

    result = decide("what's the new salary band?", general, [salary_band])

    assert result.action == "broker"
    assert result.broker_owner_id == "sam"
    assert result.blocked_candidate_ids == ["m1"]


def test_fixture2_general_fact_asked_in_general_allows() -> None:
    """Hard gate passes, soft gate (stubbed) allows -> allow."""
    mundane_fact = Candidate(
        message_id="m2",
        text="deploy went out fine, lunch is at noon",
        author_id="rahul",
        source_channel_id="general",
        source_audience={"dana", "sam", "rahul", "priya"},
        confidential_marker=False,
    )
    general = Venue(
        channel_id="general",
        channel_name="#general",
        is_dm=False,
        audience={"dana", "sam", "rahul", "priya"},
    )
    stub_decision = Decision(action="allow", answer="Deploy went out fine.", reason="Everyone here already saw this in #general.")
    client = _FakeClient(stub_decision)

    result = decide("did the deploy go out?", general, [mundane_fact], client=client)

    assert result.action == "allow"
    assert client.models.calls == 1


def test_allow_with_null_answer_falls_back_to_top_candidate_text() -> None:
    """The model can return action='allow' with answer=None — seen for
    real against the live Gemini call. decide() must not let that reach
    the stage silent: fall back to the top surviving candidate's own
    text, deterministically, no second model call."""
    mundane_fact = Candidate(
        message_id="m2",
        text="deploy went out fine, lunch is at noon",
        author_id="rahul",
        source_channel_id="general",
        source_audience={"dana", "sam", "rahul", "priya"},
        confidential_marker=False,
    )
    general = Venue(
        channel_id="general",
        channel_name="#general",
        is_dm=False,
        audience={"dana", "sam", "rahul", "priya"},
    )
    null_answer_decision = Decision(action="allow", answer=None, reason="Fine to share.")
    client = _FakeClient(null_answer_decision)

    result = decide("did the deploy go out?", general, [mundane_fact], client=client)

    assert result.action == "allow"
    assert result.answer == mundane_fact.text
    assert client.models.calls == 1  # no retry, no second call


def test_one_line_truncates_paragraph_at_last_full_word_no_append() -> None:
    """SPEC §4: reason is one line, shown verbatim. A 60-word model
    paragraph must never reach the screen — hard guard, no ellipsis."""
    paragraph = (
        "This information is highly sensitive and touches on a personnel "
        "matter that has not yet been formally communicated to the person "
        "it concerns, so sharing it here risks real harm before that "
        "conversation happens through the proper channel."
    )
    assert len(paragraph) > 140

    result = _one_line(paragraph)

    assert len(result) <= 140
    assert not result.endswith(("...", "…"))  # nothing appended
    assert paragraph.startswith(result)  # truncated, not rewritten
    assert paragraph[len(result) : len(result) + 1] in (" ", "")  # cut on a word boundary


def test_fixture3_confidential_fact_in_subset_dm_brokers_even_though_hard_gate_passes() -> None:
    """The differentiator. Hard gate passes (DM audience is a subset of
    #leadership's). The stub model (wrongly) says 'allow'. decide() must
    still downgrade to broker because of confidential_marker=True — this
    is the case a naive ACL system would leak and ours does not."""
    confidential_fact = Candidate(
        message_id="m3",
        text="Priya's resigning Friday — don't spread it until she's told her team",
        author_id="sam",
        source_channel_id="leadership",
        source_audience={"dana", "sam"},
        confidential_marker=True,
    )
    dm_dana_sam = Venue(
        channel_id="dm_dana_sam",
        channel_name="DM: Dana, Sam",
        is_dm=True,
        audience={"dana", "sam"},
    )
    # The model is wrong on purpose here — proves the override doesn't
    # depend on the model getting it right.
    wrong_stub_decision = Decision(
        action="allow",
        answer="Priya's resigning Friday.",
        reason="Model incorrectly thought this was fine to share.",
    )
    client = _FakeClient(wrong_stub_decision)

    result = decide(
        "why has Priya been quiet lately?",
        dm_dana_sam,
        [confidential_fact],
        client=client,
    )

    assert result.action == "broker"
    assert result.broker_owner_id == "sam"
    assert client.models.calls == 1  # the LLM call still happened
