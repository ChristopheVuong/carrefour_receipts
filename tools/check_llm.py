"""Smoke-test the configured LLM endpoint (ASSISTANT_LLM_BASE_URL + ASSISTANT_MODEL).

Sends a minimal chat completion request and prints latency + the reply.
Exits non-zero on auth / connection failure so it can be used in CI.

Usage:
    uv run tools/check_llm.py
"""

from __future__ import annotations

import sys
import time

from openai import OpenAI

from carrefour_receipts_api import config

PROBE = "Reply with exactly: OK"


def main() -> None:
    print(f"base_url : {config.ASSISTANT_LLM_BASE_URL}")
    print(f"model    : {config.ASSISTANT_MODEL}")
    print(f"api_key  : {'set' if config.ASSISTANT_LLM_API_KEY else 'MISSING'}\n")

    if not config.ASSISTANT_LLM_API_KEY:
        print("ERROR: ASSISTANT_LLM_API_KEY is not set — check your .env", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(
        api_key=config.ASSISTANT_LLM_API_KEY,
        base_url=config.ASSISTANT_LLM_BASE_URL or None,
    )

    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=config.ASSISTANT_MODEL,
        messages=[{"role": "user", "content": PROBE}],
        max_tokens=16,
        temperature=0,
    )
    elapsed = time.perf_counter() - t0

    reply = response.choices[0].message.content or ""
    tokens_in = response.usage.prompt_tokens if response.usage else "?"
    tokens_out = response.usage.completion_tokens if response.usage else "?"

    print(f"reply    : {reply!r}")
    print(f"tokens   : {tokens_in} in / {tokens_out} out")
    print(f"latency  : {elapsed:.2f}s")
    print("\nLLM endpoint OK")


if __name__ == "__main__":
    main()
