"""Post the deterministic demo corpus into the configured Slack workspace.

Run once after the app has joined the four named channels:

    PYTHONPATH=.. .venv/bin/python -m context_window.seed.seed_slack

Each post uses Slack's supported `username` override for the visual demo. Slack
still records the app as the technical sender, so `.seed_state.json` maps the
returned message id to the canonical seed author (`dana`, `sam`, etc.).
`store.ingest` reads that local map; no Slack user impersonation is attempted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from slack_sdk import WebClient

from context_window.seed.workspace import SeedChannel, build_workspace
from context_window.slack_client import get_slack_client


STATE_PATH = Path(__file__).with_name(".seed_state.json")


def _load_state() -> dict[str, dict[str, str]]:
    if not STATE_PATH.exists():
        return {"posted": {}, "authors": {}}
    return json.loads(STATE_PATH.read_text())


def _save_state(state: dict[str, dict[str, str]]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def _channel_ids(client: WebClient) -> dict[str, str]:
    channels: dict[str, str] = {}
    cursor: str | None = None
    while True:
        response = client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200,
            cursor=cursor,
        ).data
        for channel in response["channels"]:
            if channel.get("is_member"):
                channels[channel["name"]] = channel["id"]
        cursor = response.get("response_metadata", {}).get("next_cursor") or None
        if cursor is None:
            return channels


def _require_channel(channel: SeedChannel, ids: dict[str, str]) -> str:
    try:
        return ids[channel.name]
    except KeyError as exc:
        raise RuntimeError(f"App is not a member of #{channel.name}; invite it before seeding.") from exc


def seed(client: WebClient) -> int:
    workspace = build_workspace()
    channel_ids = _channel_ids(client)
    state = _load_state()
    posted = 0

    for channel in workspace.channels:
        # The soft-gate demo asks in a live Naman↔bot DM; an app cannot seed a
        # private human↔human DM it does not belong to.
        if channel.is_dm:
            continue
        channel_id = _require_channel(channel, channel_ids)
        for index, message in enumerate(workspace.messages_in(channel.key)):
            state_key = f"{channel.key}:{index}"
            if state["posted"].get(state_key):
                continue
            author = workspace.user(message.author_key)
            response = client.chat_postMessage(
                channel=channel_id,
                text=message.text,
                username=author.real_name,
                icon_emoji=":speech_balloon:",
            ).data
            message_id = f"{channel_id}:{response['ts']}"
            state["posted"][state_key] = message_id
            state["authors"][message_id] = author.key
            _save_state(state)
            posted += 1

    return posted


if __name__ == "__main__":
    count = seed(get_slack_client())
    print(f"Seeded {count} messages. Re-run is safe; already posted messages are skipped.")
