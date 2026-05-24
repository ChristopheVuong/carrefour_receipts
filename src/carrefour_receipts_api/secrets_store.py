"""Read/write the local secrets file (``data/secrets.yml``) — no heavy dependencies.

The Carrefour loyalty/Pass card numbers (PII, query params for the receipt/loyalty
endpoints) are persisted here by the auth service so the extractor picks them up on
its next run without hand-editing ``.env``. ``config`` reads this file as a fallback
*after* the matching environment variable, so ``.env`` always wins as an override.

The file is git-ignored (lives under ``data/``); never commit it or log its values.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def read_secrets(path: str | Path) -> dict[str, str]:
    """Load the YAML secrets file; return ``{}`` if it is absent, empty or malformed."""
    file = Path(path)
    if not file.exists():
        return {}
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None}


def write_secrets(path: str | Path, **fields: str | None) -> dict[str, str]:
    """Merge non-empty ``fields`` into the YAML secrets file and return the result.

    Existing keys not named in ``fields`` are preserved; empty/``None`` values are
    ignored (so a blank form field never wipes a stored number). Parent dirs are
    created as needed.
    """
    file = Path(path)
    merged = read_secrets(file)
    for key, value in fields.items():
        if value is not None and str(value).strip():
            merged[key] = str(value).strip()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(yaml.safe_dump(merged, default_flow_style=False), encoding="utf-8")
    return merged
