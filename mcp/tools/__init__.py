"""
MCP tool modules — each file registers tools against the shared ``mcp`` server.

Import ``register_all_tools()`` to register every tool group at once.
"""


def register_all_tools() -> None:
    """Import all tool modules so their @mcp.tool() decorators fire."""
    from tools import capacity  # noqa: F401
    from tools import costs  # noqa: F401
    from tools import inference  # noqa: F401
    from tools import jobs  # noqa: F401
    from tools import models  # noqa: F401
    from tools import stacks  # noqa: F401
    from tools import storage  # noqa: F401
