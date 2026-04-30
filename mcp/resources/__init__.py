"""
MCP resource modules — each file registers resources against the shared ``mcp`` server.

Import ``register_all_resources()`` to register every resource group at once.
"""


def register_all_resources() -> None:
    """Import all resource modules so their @mcp.resource() decorators fire."""
    from resources import ci  # noqa: F401
    from resources import clients  # noqa: F401
    from resources import config  # noqa: F401
    from resources import demos  # noqa: F401
    from resources import docs  # noqa: F401
    from resources import iam_policies  # noqa: F401
    from resources import infra  # noqa: F401
    from resources import k8s  # noqa: F401
    from resources import scripts  # noqa: F401
    from resources import source  # noqa: F401
    from resources import tests  # noqa: F401
