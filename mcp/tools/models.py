"""Model weight management MCP tools."""

import cli_runner
from audit import audit_logged
from server import mcp


@mcp.tool()
@audit_logged
def list_models() -> str:
    """List all uploaded model weights in the S3 bucket."""
    return cli_runner._run_cli("models", "list")


@mcp.tool()
@audit_logged
def get_model_uri(model_name: str) -> str:
    """Get the S3 URI for a model (for use with --model-source).

    Args:
        model_name: Name of the model.
    """
    return cli_runner._run_cli("models", "uri", model_name)
