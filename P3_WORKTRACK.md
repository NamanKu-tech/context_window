# P3 Work Tracker — Credibility and Film

## Goal

Make the project credible, measurable, and easy to understand in the demo:

- A realistic seeded Slack workspace.
- A visual audience card that makes a withheld answer legible.
- An evaluation that proves both safety and usefulness, including under attack.
- A README with only measured claims.
- A short, clear demo video once Phase 1 is green.

## Current status

- [x] Seed corpus exists in `seed/workspace.py`.
- [ ] Team chooses the canonical seed-story version before probes are finalized.
- [ ] P1 fixes the package/contracts issue so Python and the offline eval can run.
- [ ] P2 posts the selected corpus and exposes the real Slack retrieval path.

## P3 work — can start now

### 1. Decide and document the canonical dataset

- [ ] Ask the team to choose one source of truth: the current seed corpus or §6.6 of `NEED_TO_KNOW_SPEC.md`.
- [ ] Once agreed, record the canonical cast, channel memberships, three planted facts, owners, and expected venues here.
- [ ] Align `README.md` and `seed/workspace.py` to that decision.
- [ ] Do not create final eval expectations until this is settled.

### 2. Audit / finish `seed/workspace.py`

- [x] Build an offline corpus with mundane surrounding messages.
- [x] Define users, channels, messages, planted facts, fake IDs, and audience lookup.
- [x] Add self-checks for message authorship and planted-fact needles.
- [ ] Resolve its imports with P1's final package/contract structure.
- [ ] Verify it runs from the project command specified by the team.
- [ ] Confirm the corpus contains the three final, agreed demo facts.
- [ ] Add the three injection-attempt messages to `#general`.

### 3. Build the audience card (`surfaces/slack_card.py`)

- [ ] Create a function that turns a blocked decision into Slack Block Kit blocks.
- [ ] Show source audience as an avatar row plus its person count.
- [ ] Show current-channel audience as an avatar row plus its person count.
- [ ] Clearly state how many current viewers were not part of the source audience.
- [ ] Include: “Holding. Asking <owner>…” (using the actual owner).
- [ ] Fetch `profile.image_24` through Slack `users_info` and cache it.
- [ ] Keep every Block Kit `context` block to at most 10 elements: max 9 avatars plus `+N`.
- [ ] Test with 0, 1, 9, 10, and more than 10 people.
- [ ] Hand P2 a small rendering interface and an example payload for app integration.

### 4. Create the probe set (`eval/probes.yaml`)

- [ ] Create 40 normal probes with: `question`, `venue_channel`, `asker`, `expected_action`.
- [ ] Include `allow` probes: safety alone is not success; useful answers matter too.
- [ ] Cover all three planted facts in both safe and unsafe venues.
- [ ] Cover no-result / ordinary-content cases.
- [ ] Add 8 injection probes.
- [ ] For injection probes, use the three required prompt-injection patterns in `#general`.
- [ ] Verify that injection probes seeking protected facts expect `broker` or `redact`, never an unsafe `allow`.
- [ ] Validate YAML loading and required fields.

### 5. Build the evaluation harness (`eval/run_eval.py`)

- [ ] Make it run offline against the seed corpus.
- [ ] Implement a naive-retrieval arm (no gates).
- [ ] Implement a hard-gate-only arm.
- [ ] Implement a hard-plus-soft-gate arm.
- [ ] Implement an “under attack” arm with injection preambles.
- [ ] Calculate leak rate for protected facts.
- [ ] Calculate usefulness rate for expected `allow` cases.
- [ ] Print a four-arm, two-metric table.
- [ ] Write `chart.png`.
- [ ] Add a check that the under-attack leak rate equals the clean hard-plus-soft result.
- [ ] Run and record the actual results; do not invent a number.

## P3 work — waits for P1 / P2

### P1 dependencies

- [ ] Resolve the root-level `types.py` name collision with Python's standard-library `types` module.
- [ ] Choose and implement one package name consistently (`needtoknow` or `context_window`).
- [ ] Provide the frozen contracts, including the confidentiality-marker helper used by the seed data.
- [ ] Provide a runnable `policy.decide()` so the eval can exercise hard and soft arms.

### P2 dependencies

- [ ] Confirm the bot can read channel history for every seeded conversation.
- [ ] Post the agreed seed corpus into Slack.
- [ ] Provide real channel audience data to the card renderer.
- [ ] Integrate the audience-card payload when the policy returns `broker`.

## README and demo video

### README

- [x] Explain why a multi-person Slack channel is necessary for the product.
- [ ] Lead with the measured leak-rate/usefulness result once `run_eval.py` has run.
- [ ] Add the injection-safety claim only once supported by the under-attack result.
- [ ] Update the runnable command and project layout after P1 resolves packaging.

### Video — begin only once Phase 1 is green

- [ ] Record one screen with Dana asking the same question in three venues.
- [ ] Show different outcomes caused by the audiences, not by a changed asker or question.
- [ ] Show the audience card for a blocked answer.
- [ ] Show the fact owner receiving and approving/denying the broker request.
- [ ] Show the attributed answer appearing in the original thread.
- [ ] Show the evaluation chart briefly.
- [ ] Record a safety take before any Phase 2/3 stretch work.

## Team decisions to resolve before final eval

1. **Canonical dataset:** The present seed/README and §6.6 of the spec describe different casts, memberships, DM participants, and confidential facts. Pick one and align all files before locking probes.
2. **Package/contracts:** Python cannot currently run from the repo root because `types.py` shadows the standard library. P1 must settle the package layout and frozen imports before P3 can execute the seed or eval path.

## Definition of done for P3

- [ ] The seed corpus is canonical, validates, and is posted by P2.
- [ ] Blocked answers display an audience card with the difference visible.
- [ ] The 40 normal probes and 8 injection probes run in the harness.
- [ ] The output includes four arms, leak rate, usefulness rate, and `chart.png`.
- [ ] The attack arm does not worsen leakage.
- [ ] README contains measured—not promised—results.
- [ ] The Phase 1 demo video clearly shows the audience decision and broker loop.
