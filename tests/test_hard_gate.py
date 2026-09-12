"""SPEC §6.2 acceptance test for hard_gate() — no Slack, no network.

Fixtures are hand-built Venue/Candidate objects, not retrieved from
anything. This is the floor: pure-Python set-membership math that runs
before any model call.
"""

from context_window.policy import hard_gate
from context_window.types import Candidate, Venue


def test_fact_from_leadership_asked_in_general_blocks() -> None:
    """Source #leadership, asked in #general → hard_gate must fail."""
    leadership = Candidate(
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

    assert hard_gate(leadership, general) is False


def test_fact_from_general_asked_in_general_allows() -> None:
    """Source #general, asked in #general → hard_gate must pass."""
    general_fact = Candidate(
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

    assert hard_gate(general_fact, general) is True


def test_confidential_leadership_fact_asked_in_subset_dm_passes_hard_gate() -> None:
    """Source #leadership (confidential_marker=True), asked in a DM that is
    a strict subset of #leadership's membership.

    hard_gate returns True here — permission is real, everyone in the DM
    could legitimately have seen the source. This fixture must currently
    stay green on `hard_gate` alone; it is the soft gate (not yet written)
    that is supposed to catch it and downgrade allow -> broker because of
    the confidentiality marker. Without the soft gate, this candidate
    would leak straight through. That gap is the project's entire
    differentiator (SPEC §6.2, §6.6 fact #3) — this test exists to prove
    the case is reachable, not to prove it's handled yet.
    """
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
        audience={"dana", "sam"},  # subset (here, equal) of #leadership's {dana, sam} — SPEC §6.6
    )

    assert hard_gate(confidential_fact, dm_dana_sam) is True
    # TODO(soft gate, next increment): decide() must downgrade this
    # allow -> broker because confidential_marker=True. hard_gate alone
    # has no way to see that — it only ever looks at audience sets.
