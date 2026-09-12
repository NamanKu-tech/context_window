"""Shared Slack Web API client for the P2 read and delivery layer."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from slack_sdk import WebClient


def get_slack_client() -> WebClient:
    """Return the project's one Slack WebClient.

    CopilotKit owns event ingress. This client is deliberately limited to the
    Slack Web API operations P2 and the broker need: reads, seeding, and DMs.
    """
    load_dotenv()
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing SLACK_BOT_TOKEN in .env")
    return WebClient(token=token)
