"""Slack ingestion, audience resolution, and SQLite FTS5 retrieval for P2."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from slack_sdk import WebClient

from context_window.contracts import Candidate, Venue
from context_window.markers import has_confidential_marker


DB_PATH = Path(os.environ.get("STORE_DB_PATH", Path(__file__).with_name("need_to_know.db")))
_audience_cache: dict[str, set[str]] = {}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
            message_id UNINDEXED,
            channel_id UNINDEXED,
            author_id UNINDEXED,
            ts UNINDEXED,
            text
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_audiences (
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL,
            is_dm INTEGER NOT NULL,
            members_json TEXT NOT NULL
        )
        """
    )
    return connection


def _pages(method: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
    """Yield Slack cursor-paginated responses without custom retry machinery."""
    cursor: str | None = None
    while True:
        response = method(cursor=cursor, **kwargs) if cursor else method(**kwargs)
        yield response.data
        cursor = response.data.get("response_metadata", {}).get("next_cursor") or None
        if cursor is None:
            return


def _audience(client: WebClient, channel_id: str) -> set[str]:
    if channel_id not in _audience_cache:
        members: set[str] = set()
        for response in _pages(client.conversations_members, channel=channel_id, limit=200):
            members.update(response["members"])
        _audience_cache[channel_id] = members
    return _audience_cache[channel_id]


def _channel_metadata(client: WebClient, channel_id: str) -> tuple[str, bool]:
    channel = client.conversations_info(channel=channel_id).data["channel"]
    return channel.get("name") or channel_id, bool(channel.get("is_im") or channel.get("is_mpim"))


def _record_audience(
    connection: sqlite3.Connection,
    channel_id: str,
    channel_name: str,
    is_dm: bool,
    audience: set[str],
) -> None:
    connection.execute(
        """
        INSERT INTO channel_audiences(channel_id, channel_name, is_dm, members_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            channel_name = excluded.channel_name,
            is_dm = excluded.is_dm,
            members_json = excluded.members_json
        """,
        (channel_id, channel_name, is_dm, json.dumps(sorted(audience))),
    )


def ingest(client: WebClient) -> None:
    """Ingest every conversation the bot belongs to and cache its audience once."""
    bot_user_id = client.auth_test().data.get("user_id")
    with _connect() as connection:
        for page in _pages(
            client.conversations_list,
            exclude_archived=True,
            limit=200,
            types="public_channel,private_channel,im,mpim",
        ):
            for channel in page["channels"]:
                if not channel.get("is_member"):
                    continue

                channel_id = channel["id"]
                audience = _audience(client, channel_id)
                channel_name = channel.get("name") or channel_id
                is_dm = bool(channel.get("is_im") or channel.get("is_mpim"))
                _record_audience(connection, channel_id, channel_name, is_dm, audience)

                # A re-ingest is a fresh snapshot. Clearing this channel first
                # removes notices that may have been indexed by older builds
                # and prevents deleted Slack messages from lingering as answers.
                connection.execute("DELETE FROM messages WHERE channel_id = ?", (channel_id,))

                for history_page in _pages(
                    client.conversations_history,
                    channel=channel_id,
                    limit=200,
                ):
                    for message in history_page["messages"]:
                        # Slack emits join/leave/archive and other system notices
                        # in channel history. They are not conversational facts
                        # and made broad questions retrieve irrelevant private
                        # channels, so never place them in the answer index.
                        if message.get("subtype") or message.get("type", "message") != "message":
                            continue
                        author_id = message.get("user")
                        text = message.get("text")
                        ts = message.get("ts")
                        if not author_id or not text or not ts:
                            continue
                        # A mention is a request to the agent, not a fact the
                        # agent should later retrieve as an answer. Keeping it
                        # would make questions echo themselves above the real
                        # channel message that prompted the answer.
                        if bot_user_id and text.lstrip().startswith(f"<@{bot_user_id}>"):
                            continue
                        message_id = message.get("client_msg_id") or f"{channel_id}:{ts}"
                        connection.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
                        connection.execute(
                            """
                            INSERT INTO messages(message_id, channel_id, author_id, ts, text)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (message_id, channel_id, author_id, ts, text),
                        )


def build_venue(client: WebClient, channel_id: str) -> Venue:
    """Build the audience-aware venue for one incoming Slack conversation."""
    channel_name, is_dm = _channel_metadata(client, channel_id)
    audience = _audience(client, channel_id)
    with _connect() as connection:
        _record_audience(connection, channel_id, channel_name, is_dm, audience)
    return Venue(
        channel_id=channel_id,
        channel_name=channel_name,
        is_dm=is_dm,
        audience=set(audience),
    )


def _fts_query(question: str) -> str | None:
    terms = [term for term in re.findall(r"[A-Za-z0-9_]+", question.lower()) if len(term) > 2]
    if not terms:
        return None
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


def search(query: str, limit: int = 8) -> list[Candidate]:
    """Return FTS5 matches with their persisted source-audience sets."""
    if limit < 1:
        return []
    fts_query = _fts_query(query)
    if fts_query is None:
        return []

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT m.message_id, m.text, m.author_id, m.channel_id, a.members_json
            FROM messages AS m
            JOIN channel_audiences AS a ON a.channel_id = m.channel_id
            WHERE messages MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()

    return [
        Candidate(
            message_id=message_id,
            text=text,
            author_id=author_id,
            source_channel_id=channel_id,
            source_audience=set(json.loads(members_json)),
            confidential_marker=has_confidential_marker(text),
        )
        for message_id, text, author_id, channel_id, members_json in rows
    ]
