"""Single source of truth for model access — SPEC §5.

One place, one definition: `policy.py` and P3's `eval/` must both use the
exact same client and model, so it lives here, not duplicated in either.

OpenRouter is preferred when ``OPENROUTER_API_KEY`` is present. One failed
OpenRouter call falls back to Gemini when ``GEMINI_API_KEY`` is present. There
are no retries: the fallback is a provider change, not a repeated request.

Lazy on purpose: importing this module never requires either key to be set.
The Gemini client is constructed (and cached) only when it is needed.

Run `python -m context_window.config` as an all-day smoke test: prints
the model name, makes one trivial structured call, and prints OK or the
exact error. Keep it to ten seconds — no retries.

Internal id space is the seed key ("dana", "sam", ...). `store.py` translates real Slack ids into it at ingest.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, TypeVar

from dotenv import load_dotenv

if TYPE_CHECKING:
    from google import genai

load_dotenv()  # picks up .env if present; no-op (not an error) if it isn't

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

_client: genai.Client | None = None
ResponseModel = TypeVar("ResponseModel")


def get_client() -> genai.Client:
    """Return the shared Gemini client, constructing it on first call."""
    global _client
    if _client is None:
        from google import genai as _genai

        _client = _genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _generate_with_gemini(
    system_instruction: str, user_prompt: str, response_model: type[ResponseModel]
) -> ResponseModel:
    from google.genai import types

    response = get_client().models.generate_content(
        model=DEFAULT_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_model,
        ),
    )
    if isinstance(response.parsed, response_model):
        return response.parsed
    raise ValueError(f"Gemini returned no parseable {response_model.__name__}")


def _generate_with_openrouter(
    system_instruction: str, user_prompt: str, response_model: type[ResponseModel]
) -> ResponseModel:
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        max_retries=0,
    )
    completion = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__.lower(),
                "strict": True,
                "schema": response_model.model_json_schema(),
            },
        },
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError(f"OpenRouter returned no {response_model.__name__} content")
    return response_model.model_validate_json(content)


def generate_structured(
    system_instruction: str, user_prompt: str, response_model: type[ResponseModel]
) -> ResponseModel:
    """Make one structured call, preferring OpenRouter then Gemini.

    Gemini remains the sole provider when no OpenRouter key is configured.
    If OpenRouter is configured but fails, Gemini is tried once only when its
    key is available; otherwise the original OpenRouter error is surfaced.
    """
    if os.environ.get("OPENROUTER_API_KEY"):
        try:
            return _generate_with_openrouter(system_instruction, user_prompt, response_model)
        except Exception:
            if not os.environ.get("GEMINI_API_KEY"):
                raise
    return _generate_with_gemini(system_instruction, user_prompt, response_model)


if __name__ == "__main__":
    import sys

    from pydantic import BaseModel

    provider = "openrouter" if os.environ.get("OPENROUTER_API_KEY") else "gemini"
    model = OPENROUTER_MODEL if provider == "openrouter" else DEFAULT_MODEL
    print(f"provider: {provider}\nmodel: {model}")
    try:
        class _Ping(BaseModel):
            ok: bool

        response = generate_structured(
            "Return only the requested JSON.",
            'Reply with the JSON object {"ok": true}.',
            _Ping,
        )
        if response.ok:
            print("OK")
        else:
            print(f"UNEXPECTED RESPONSE: {response!r}")
            sys.exit(1)
    except Exception as e:  # noqa: BLE001 — smoke test wants the exact error, not a traceback hunt
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
