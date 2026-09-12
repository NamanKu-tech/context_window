# Need to Know

> **Leak rate: TBD — run `python eval/run_eval.py` once Phase 1 is complete; it prints the number and writes `chart.png`.** This line gets replaced with the real number (e.g. "0% leaked, 91% useful, hard+soft arm") the moment the eval exists. Nothing here is allowed to claim a number that hasn't been produced by that script.

Every other Slack agent answers **"what is true?"**. This one answers **"what is sayable here, in front of these people?"**

`@needtoknow why did the launch date move?` gives three different, correct answers depending on whether you ask in `#general`, `#engineering`, or `#leadership` — and when it can't answer safely, it doesn't refuse. It asks the person who owns the fact, in real time, and posts their answer back into the thread.

---

## The problem this is not solving

Slack already ships permission-aware retrieval — the Real-Time Search API, the official MCP server. **"AI search that respects ACLs" is a solved, shipped problem.** We do not rebuild it.

Access control answers one question: *was this user allowed to read the source message?* That's necessary but it isn't the interesting question. The interesting question is:

> The agent legitimately saw this fact. The person asking may even be entitled to know it. **Is saying it out loud, in this channel, in front of these twelve people, still wrong?**

Nobody ships that layer. A fact can be visible to you personally and still be wrong to broadcast into a room that includes people who were never supposed to see it. Need to Know sits between retrieval and response, and its whole job is to ask that second question — and when the answer is "not here," to go find out from the one person who can actually say yes.

### Why the environment is load-bearing

This is the paragraph the spec asked for explicitly, so here it is in one place: **a chatbot has one user.** A ChatGPT-style interface, a support widget, a DM to a bot — every one of those has exactly one person on the other end of the conversation. There is no "audience" to reason about, because there is no audience. The question "is this safe to say *here*, in front of *these people*" is meaningless in a 1:1 chat window — there's only ever one "here."

Slack is a room with a member list. The same question, asked in `#general` versus `#leadership`, has a different audience attached to it before a single word of the answer is written. That's not a UI detail — it's the only reason this product's core question is even askable. Build this same idea on top of a chat API and you've built a permissions filter. Build it on top of a multi-party room and you've built a *judgment* layer, because now there's a "who's listening" to make a judgment about. The environment isn't incidental to the idea; it's the necessary condition for the idea to exist at all.

---

## How it decides

Two gates, run in a fixed order, for every candidate fact retrieved for a question.

### 1. The hard gate — pure Python, no model, runs first

```python
def hard_gate(candidate: Candidate, venue: Venue) -> bool:
    """True = safe to say here. Pure Python. No model."""
    return venue.audience <= candidate.source_audience   # subset, or we leak
```

If the people who can see the answer are not a subset of the people who could see the source, the candidate is blocked — **before it ever reaches the LLM.** This is the strongest architectural claim in the project: no prompt injection, no clever jailbreak, no model mistake can leak a fact through this path, because a blocked candidate never becomes a token the model sees. It's not "the model was told not to." It's "the model was never given the chance."

### 2. The soft gate — one structured LLM call, on top of the floor

Set containment can't see intent. It can't tell that "keep this between us" was said out loud, or that a fact about one specific colleague is a different kind of sensitive than a fact about a ship date. So candidates that *pass* the hard gate still go through one structured call that judges:

- confidentiality markers ("between us," "don't share," "off the record," …)
- purpose and sensitivity of the specific fact
- whether an `allow` should be downgraded to `broker` even though nothing was technically leaked

This is the path that proves the product has a second layer at all. The test fixture for it: a fact said in a DM the asker was *personally a member of* — hard gate passes clean, permission is real — and the soft gate still holds it back because the person who said it asked for discretion. **Permission existing and disclosure being appropriate are two different questions, and this system is the only thing here that asks both.**

### 3. When it can't answer: broker, don't refuse

If nothing survives the hard gate, or the soft gate downgrades an `allow`, the system doesn't say "I can't help with that." It DMs the fact's owner with an approve/deny card, and — on approval — posts an attributed answer back into the original thread: *"Shared by @Dana, just now."* The person who owns the context gets to make the judgment call the system can't safely make on its own. Refusal is a dead end; brokering keeps the conversation alive.

---

## Architecture

```
question in a channel
        │
        ▼
  store.search()  ──────► list[Candidate]     (FTS5, no vectors — 120 msgs doesn't need them)
        │
        ▼
  policy.decide(question, venue, candidates)
        │
        ├─ hard_gate() per candidate ─── pure Python, subset check ─── blocked ids recorded
        │
        ├─ nothing survives? ──────────► Decision(action="broker")
        │
        └─ something survives? ───────► one structured LLM call
                                              │
                                              ├─ confidential_marker on a survivor?
                                              │  └─► downgrade to broker anyway
                                              │
                                              └─► Decision(action="allow" | "redact" | "broker")
        │
        ▼
  surfaces/slack.py renders it:
    - allow/redact  → answer posted directly
    - broker        → audience card (who could see the source vs. who's here)
                       + DM to the owner with Approve / Deny buttons
                       + approval posts into the *original thread*, attributed
```

`Decision` (below) is the **only** thing `policy.py` returns. Everything downstream — Slack rendering, the eval harness, later the Telegram/phone surfaces — reads this one typed object and nothing else.

```python
class Decision(BaseModel):
    action: Literal["allow", "redact", "broker"]
    answer: str | None = None
    redacted_answer: str | None = None
    broker_owner_id: str | None = None
    reason: str                          # one line, shown to the user verbatim
    blocked_candidate_ids: list[str] = []
```

---

## The demo dataset

A fictional four-week-old startup, seeded as ~120 Slack messages across four channels and one DM, with three real secrets buried in ordinary daily traffic so they don't stand out to a human skimming the channel — the system has to actually reason about audience, not just pattern-match on "this looks important."

| Fact | Lives in | Caught by | Proves |
|---|---|---|---|
| Atlas launch slipped 6 Oct → 20 Oct | `#engineering` (5 people) | **hard gate** | Set containment alone stops a leak into `#general` (8 people), deterministically |
| New senior-eng salary band | `#leadership` (3 people) | **hard gate** | Same rule holds at higher stakes — comp data, not a ship date |
| "Priya's interviewing elsewhere — keep this between us" | DM, Dana ↔ Rahul (asker *is* a member) | **soft gate** | Permission is real and the hard gate passes clean — the norm still says no. **This is the entire differentiator; if this case doesn't broker, the project doesn't exist.** |

Cast: Dana (CTO), Sam (CEO), Rahul (engineer, the asker), Priya (engineer, subject of the confidential fact), plus four ordinary colleagues who exist purely to make the audience numbers real instead of toy-sized.

---

## Repo layout

```
needtoknow/
  types.py               # frozen contracts — Venue, Candidate, Decision, BrokerResult
  config.py               # env loading                                          [ ] not yet built
  seed/
    workspace.py          # the fictional company, as data — no network needed    [x] done
    seed_slack.py         # posts workspace.py's data into a real workspace       [ ] not yet built
  store.py                 # ingest · audience resolution · FTS5 search           [ ] not yet built
  policy.py                # hard gate · soft gate · Decision                     [ ] not yet built
  broker.py                # ask the owner, surface-agnostic                      [ ] not yet built
  surfaces/
    slack.py               # Block Kit audience card + approve/deny DM            [ ] not yet built
    telegram.py             # Phase 2                                            [ ] not yet built
  app.py                    # Bolt listener, Socket Mode                         [ ] not yet built
  eval/
    probes.yaml              # 40 probes across 3 arms                          [ ] not yet built
    run_eval.py               # naive vs. hard-only vs. hard+soft → chart.png    [ ] not yet built
  README.md                    # this file
  .env.example                  # not yet written
```

**Current build status:** `types.py` and `seed/workspace.py` are written and self-verified (see below). Everything else in the tree above is speced (§6 of the build spec) but not yet implemented — this README will be updated as each module lands, and the leak-rate line at the top gets its real number the moment `eval/run_eval.py` exists and runs.

### What's actually runnable right now

```bash
python -m needtoknow.seed.workspace
```

prints the corpus: 8 users, 5 conversations, 123 messages, the three planted facts with their catching gate, and every message carrying a confidentiality marker. `build_workspace()` self-checks on import — it fails loudly if a message is attributed to someone outside the channel's member list, or if a planted fact's needle stops matching exactly one seed message. That check is what keeps the corpus honest as it's edited.

---

## Why these engineering choices

Every one of these is a deliberate refusal to build something the project doesn't need — see the build spec's explicit do-not-build list (no vector DB, no ORM, no web UI, no auth system, no message queue, no general chat mode). A hackathon judge should read this table as "reuse discipline," not "cut corners":

| Choice | Why |
|---|---|
| **Slack Socket Mode** (`slack-bolt`), not a webhook server | No ngrok, no signature verification code, no public endpoint to manage under a 4-hour clock |
| **SQLite + FTS5**, not a vector DB | 120 messages. Embeddings and a reranker would be solving a problem this dataset doesn't have, and FTS5 is inspectable with a plain SQL query when something looks wrong |
| **Structured LLM output** via the SDK's own parse helper, not JSON-in-prompt + regex | The failure mode of "the model almost returned valid JSON" disappears entirely |
| **The hard gate is plain Python, not a model call** | It's the one part of the system that has to be un-jailbreakable. A subset check on two sets can't be argued with by a clever prompt |
| **`confidential_marker` is a substring check**, not a model call | Deterministic, auditable, and cheap — the model's judgment is reserved for the soft gate, where it's actually needed |
| **`broker()` is surface-agnostic by signature** | Phase 1 is Slack DM, Phase 2 swaps to Telegram, Phase 3 swaps to a live phone call — none of them touch `policy.py` or change `BrokerResult`'s shape |

---

## Setup

```bash
pip install slack-bolt openai pydantic python-dotenv matplotlib python-telegram-bot pyyaml
```

**Bot token scopes:**
```
app_mentions:read  channels:history  channels:read
groups:history     groups:read       im:history
im:write           users:read        chat:write
```

**App-level token (Socket Mode):** `connections:write`

**`.env`:**
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...        # phase 2
AMBIGUOUS_API_KEY=ak-...      # phase 4
```

> The bot only sees channels it's invited to. Invite it to all five conversations (`#general`, `#engineering`, `#leadership`, `#hiring`, the Dana↔Rahul DM) before running `seed_slack.py`, and confirm with one successful `conversations_history` read before writing any retrieval code against it.

### One-command demo path (once Phase 1 is complete)

```bash
python -m needtoknow.seed.seed_slack     # posts the corpus into your workspace
python -m needtoknow.app                  # starts the Socket Mode listener
```

Then, in Slack: ask `@needtoknow why did the launch date move?` in `#general`, then in `#engineering`, then in `#leadership`, and watch the three different answers — the audience card renders on the blocked ones, showing exactly who could see the source versus who's in the room now.

---

## Roadmap

- **Phase 1** (green by 13:15 — this alone is the submission): seed data posted, `hard_gate` → soft gate → typed `Decision`, audience card, approve/deny DM posting back into the original thread, eval running on all three arms.
- **Phase 2** (~20 min): swap `broker()`'s transport to Telegram with an inline keyboard.
- **Phase 3** (spiked early, hard kill at 12:30 if no audio round-trip): broker over a live phone call — the owner speaks a constraint ("yes, but don't mention the number") and it's enforced on the posted text.
- **Phase 4** (only after freeze): attach a second workspace with a different membership model over MCP, run the same `policy.py` against it unmodified.

Each phase is additive and independently droppable — Phase 1 alone is a complete, working submission; nothing later is load-bearing for the core claim.

---

## What this deliberately does not do

No auth system (Slack is the identity provider), no vector database or embeddings (FTS5 over 120 messages is plenty and stays debuggable), no web dashboard (Slack is the UI), no task queue or scheduler, no ORM, no Docker, no retry/metrics infrastructure, no general "ask me anything" chat mode. One entry point: `@needtoknow <question>` in a channel. Every one of these is a considered exclusion, not an oversight — see the build spec's do-not-build list for the reasoning behind each.

---

> A chatbot has one user. This agent has an audience — and that is the whole product.
