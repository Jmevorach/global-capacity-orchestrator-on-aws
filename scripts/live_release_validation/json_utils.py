"""Strict JSON decoding helpers for security-sensitive validation state."""

from __future__ import annotations

import json
from typing import Any


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def loads_without_duplicate_keys(value: str) -> Any:
    """Decode JSON while rejecting duplicate keys at every object depth."""
    return json.loads(value, object_pairs_hook=_reject_duplicate_keys)
