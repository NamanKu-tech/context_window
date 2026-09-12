# P3 Work Tracker — Credibility and Film

## Goal

Make the project credible, measurable, and easy to understand in the demo:

- A realistic seeded Slack workspace.
- Three constrained Slack UI components that make a decision and withheld answer legible.
- An evaluation that proves both safety and usefulness, including under attack.
- A README with only measured claims.
- A short, clear demo video once Phase 1 is green.

## Current status

- [x] Seed corpus exists in `seed/workspace.py`.
- [x] Canonical seed story is §6.6 of `NEED_TO_KNOW_SPEC.md` (Dana/Sam DM; Priya resigning case).
- [ ] P1 fixes the package/contracts issue so Python and the offline eval can run.
- [ ] P2 posts the selected corpus and exposes the real Slack retrieval path.

## P3 work — can start now

### 1. Align the canonical dataset

- [x] Use §6.6 of `NEED_TO_KNOW_SPEC.md` as the source of truth.
- [ ] Record the canonical cast, channel memberships, three planted facts, owners, and expected venues here.
- [ ] Align `README.md` and `seed/workspace.py` to that decision.
- [ ] Do not create final eval expectations until this is settled.

### 2. Audit / finish `seed/workspace.py`

- [x] Build an offline corpus with mundane surrounding messages.
- [x] Define users, channels, messages, planted facts, fake IDs, and audience lookup.
- [x] Add self-checks for message authorship and planted-fact needles.
- [ ] Resolve its imports with P1's final package/contract structure.
- [ ] Verify it runs from the project command specified by the team.
- [x] Revise the corpus to the required cast: Dana, Sam, Rahul, and Priya.
- [x] Revise channels to the required memberships: general (all four), engineering (Dana/Rahul/Priya), leadership (Dana/Sam), hiring (Dana/Sam), and DM Dana↔Sam.
- [x] Confirm the three required facts: Atlas slip, senior-eng salary band, and Sam's confidential Priya-resigning message in `#leadership`.
- [x] Add the three injection-attempt messages to `#general`.

### 3. Build constrained Channel UI (`channel/components.tsx`)

- [ ] Create `AudienceCard` with validated JSON-serializable props: `sourceAudience`, `venueAudience`, `ownerName`, and `status`.
- [ ] Show source audience as an avatar row plus its person count.
- [ ] Show current-channel audience as an avatar row plus its person count.
- [ ] Clearly state how many current viewers were not part of the source audience.
- [ ] Include: “Holding. Asking <owner>…” (using the actual owner).
- [ ] Keep generated Slack context blocks to at most 10 elements: max 9 avatars plus `+N`.
- [ ] Test with 0, 1, 9, 10, and more than 10 people.
- [ ] Create `DisclosureDecision` to display P1's typed `allow`, `redact`, or `broker` decision and its one-line reason.
- [ ] Ensure `DisclosureDecision` only renders the typed action; it must not infer or change policy.
- [ ] Define `ConsentCard` props for owner-facing Approve, Deny, and constrained-approval actions.
- [ ] Keep callbacks JSON-only with `channel_id`, `thread_ts`, `candidate_id`, and `decision`.
- [ ] Coordinate with P1: Phase 1 sends the consent DM via `surfaces/slack_broker.py` and `WebClient`; do not make the runner responsible for out-of-band DMs.
- [ ] Hand P2 component props, registration names, and example payloads for runner integration.
- [ ] Ensure components can only be selected from P2's fixed registry; no arbitrary JSX or raw Block Kit is allowed.

### 4. Create the probe set (`eval/probes.yaml`)

- [x] Create 40 normal probes with: `question`, `venue_channel`, `asker`, `expected_action`.
- [x] Include `allow` probes: safety alone is not success; useful answers matter too.
- [x] Cover all three planted facts in both safe and unsafe venues.
- [x] Cover ordinary-content cases.
- [x] Add 8 injection probes.
- [x] Use the three required prompt-injection patterns in `#general`.
- [x] Verify that injection probes seeking protected facts expect `broker`, never an unsafe `allow`.
- [x] Validate YAML loading, required fields, and exact 40 + 8 counts.

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

- [x] Rename root `types.py` to `contracts.py` to avoid shadowing Python's standard-library module.
- [ ] Finish the `context_window` package layout and update all imports consistently.
- [ ] Provide the frozen contracts, including the confidentiality-marker helper used by the seed data.
- [ ] Provide a runnable `policy.decide()` so the eval can exercise hard and soft arms.

### P2 dependencies

- [ ] Confirm one real Slack message reaches the CopilotKit Channel runner, calls `POST /decide`, and returns a reply.
- [ ] Post the agreed seed corpus into Slack.
- [ ] Provide real channel audience data and cached avatar URLs from `WebClient` / `users_info` to the component props.
- [ ] Register and render the three P3 components only after receiving P1's typed decision.

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

1. **Canonical dataset:** Resolved. §6.6 of the latest spec is authoritative. The existing seed/README must be aligned to it before probes are finalized.
2. **Package/contracts:** `types.py` has now been renamed to `contracts.py`, which fixes the standard-library collision. Python tests still cannot import `context_window`, so P1 must finish the package layout and frozen imports before P3 can execute the seed or eval path.

## Definition of done for P3

- [ ] The seed corpus is canonical, validates, and is posted by P2.
- [ ] `AudienceCard`, `DisclosureDecision`, and `ConsentCard` render through the fixed Channel component registry.
- [ ] The 40 normal probes and 8 injection probes run in the harness.
- [ ] The output includes four arms, leak rate, usefulness rate, and `chart.png`.
- [ ] The attack arm does not worsen leakage.
- [ ] README contains measured—not promised—results.
- [ ] The Phase 1 demo video clearly shows the audience decision and broker loop.
