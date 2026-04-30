"""
Audit logging infrastructure for the GCO MCP server.

Provides:
- ``_sanitize_arguments`` — redacts sensitive keys, truncates large values.
- ``audit_logged`` — decorator that emits structured JSON audit entries for
  every MCP tool invocation (success or failure).
- Startup audit log entry emitted at import time.
"""

import functools
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from version import get_project_version

# =============================================================================
# AUDIT LOGGING
# =============================================================================

_MCP_SERVER_VERSION = get_project_version()

audit_logger = logging.getLogger("gco.mcp.audit")

# Patterns for sensitive argument key names (case-insensitive)
_SENSITIVE_KEY_PATTERNS = [
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r".*password.*", re.IGNORECASE),
    re.compile(r".*key.*", re.IGNORECASE),
]

_MAX_ARG_VALUE_BYTES = 1024  # 1KB


def _sanitize_arguments(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Sanitize tool arguments for audit logging.

    - Redact values whose key name matches sensitive patterns (token, secret, password, key).
    - Truncate string values longer than 1KB to first 100 chars + '[truncated]'.
    """
    sanitized = {}
    for k, v in kwargs.items():
        # Check if the key name matches any sensitive pattern
        if any(pattern.match(k) for pattern in _SENSITIVE_KEY_PATTERNS):
            sanitized[k] = "[REDACTED]"
            continue

        # Truncate large string values
        str_val = str(v) if not isinstance(v, str) else v
        if len(str_val.encode("utf-8", errors="replace")) > _MAX_ARG_VALUE_BYTES:
            sanitized[k] = str_val[:100] + "[truncated]"
        else:
            sanitized[k] = v
    return sanitized


def audit_logged(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that logs structured JSON audit entries for MCP tool invocations."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.time()
        sanitized_args = _sanitize_arguments(kwargs)
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            audit_logger.info(
                json.dumps(
                    {
                        "event": "mcp.tool.invocation",
                        "tool": func.__name__,
                        "arguments": sanitized_args,
                        "status": "success",
                        "duration_ms": round(duration_ms, 2),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            )
            return result
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit_logger.info(
                json.dumps(
                    {
                        "event": "mcp.tool.invocation",
                        "tool": func.__name__,
                        "arguments": sanitized_args,
                        "status": "error",
                        "error": str(e)[:200],
                        "duration_ms": round(duration_ms, 2),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            )
            raise

    return wrapper


def emit_startup_log() -> None:
    """Emit the startup audit log entry."""
    audit_logger.info(
        json.dumps(
            {
                "event": "mcp.server.startup",
                "version": _MCP_SERVER_VERSION,
                "audit_log_level": logging.getLevelName(audit_logger.getEffectiveLevel()),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    )
