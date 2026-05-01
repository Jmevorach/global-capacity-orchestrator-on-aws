"""
MCP resource modules — each file registers resources against the shared ``mcp`` server.

Import ``register_all_resources()`` to register every resource group at once.
"""


def register_all_resources() -> None:
    """Import all resource modules so their @mcp.resource() decorators fire."""
    # These imports are intentionally unused — we pull them in for their
    # side effects (each module registers @mcp.resource() handlers at
    # import time). The noqa silences F401.
    from resources import (  # noqa: F401
        ci,
        clients,
        config,
        demos,
        docs,
        iam_policies,
        infra,
        k8s,
        scripts,
        source,
        tests,
    )
