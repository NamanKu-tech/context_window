"""Single source of truth for the model client — SPEC §5.

One place, one definition: `policy.py` and P3's `eval/` must both use the
exact same client and model, so it lives here, not duplicated in either.

Lazy on purpose: importing this module never requires `GEMINI_API_KEY` to
be set. The client is constructed (and cached) on first `get_client()`
call, not at import time.

Run `python -m context_window.config` as an all-day smoke test: prints
the model name, makes one trivial structured call, and prints OK or the
exact error. Keep it to ten seconds — no retries.

Internal id space is the seed key ("dana", "sam", ...). `store.py` translates real Slack ids into it at ingest.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from google import genai

load_dotenv()  # picks up .env if present; no-op (not an error) if it isn't

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Return the shared Gemini client, constructing it on first call."""
    global _client
    if _client is None:
        from google import genai as _genai

        _client = _genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


if __name__ == "__main__":
    import sys

    from pydantic import BaseModel

    print(f"model: {DEFAULT_MODEL}")
    try:
        from google.genai import types

        class _Ping(BaseModel):
            ok: bool

        response = get_client().models.generate_content(
            model=DEFAULT_MODEL,
            contents='Reply with the JSON object {"ok": true}.',
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_Ping,
            ),
        )
        if isinstance(response.parsed, _Ping) and response.parsed.ok:
            print("OK")
        else:
            print(f"UNEXPECTED RESPONSE: {response.parsed!r}")
            sys.exit(1)
    except Exception as e:  # noqa: BLE001 — smoke test wants the exact error, not a traceback hunt
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
