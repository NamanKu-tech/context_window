"""Verify that the Slack bot can read a channel and its member set.

Run from the repository root:
    .venv/Scripts/python.exe scripts/spike_slack_read.py
"""

from __future__ import annotations

import sys

from slack_sdk.errors import SlackApiError

from slack_client import get_slack_client

TARGET_CHANNEL_NAME = "new-channel"


def main() -> int:
    try:
        client = get_slack_client()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    try:
        response = client.conversations_list(
            exclude_archived=True,
            limit=200,
            types="public_channel,private_channel",
        )
        channel = next(
            (
                item
                for item in response["channels"]
                if item["name"] == TARGET_CHANNEL_NAME and item.get("is_member")
            ),
            None,
        )
        if channel is None:
            print(
                f"Bot cannot find a joined #{TARGET_CHANNEL_NAME} channel.",
                file=sys.stderr,
            )
            return 1

        members = client.conversations_members(channel=channel["id"])["members"]
    except SlackApiError as error:
        print(f"Slack API error: {error.response['error']}", file=sys.stderr)
        return 1

    print(f"Read spike passed: #{channel['name']} ({channel['id']})")
    print(f"Member count: {len(members)}")
    print("Member IDs:")
    for member_id in members:
        print(f"- {member_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
