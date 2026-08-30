"""Generation-time metadata shared by every code-diagram artifact."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

_COMMIT_RE = re.compile(r"[0-9a-fA-F]{40}")


def generation_timestamp_utc() -> str:
    """Return one ISO-8601 UTC timestamp for a generator invocation.

    ``SOURCE_DATE_EPOCH`` makes regeneration reproducible when supplied;
    otherwise the current UTC time records when the artifacts were produced.
    Timestamps intentionally use whole seconds and a trailing ``Z`` so they
    remain compact and unambiguous in HTML, PNGs, READMEs, and source markers.
    """
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is None:
        generated_at = datetime.now(UTC)
    else:
        try:
            generated_at = datetime.fromtimestamp(int(source_date_epoch), UTC)
        except (OSError, OverflowError, ValueError) as exc:
            raise ValueError(
                "SOURCE_DATE_EPOCH must be an integer Unix timestamp",
            ) from exc
    return generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")


def generation_source_commit() -> str:
    """Return the explicit Git commit whose charted source is being rendered.

    A generated artifact cannot embed the SHA of the same commit that contains
    it without becoming self-referential. Canonical generation therefore uses
    a source commit supplied by the caller and commits derived artifacts in a
    later commit. The generator separately verifies every target against this
    revision after stripping generated marker blocks.
    """
    value = os.environ.get("GCO_DIAGRAM_SOURCE_COMMIT", "").strip()
    if not _COMMIT_RE.fullmatch(value):
        raise ValueError("GCO_DIAGRAM_SOURCE_COMMIT must be an exact 40-character Git commit SHA")
    return value.lower()
