"""
CLI runner for the GCO MCP server.

Provides ``_run_cli()`` which shells out to the ``gco`` CLI with
``--output json`` and returns the result. All arguments are passed as
separate list elements (shell=False) to prevent command injection.
"""

import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def _run_cli(*args: str) -> str:
    """Run a gco CLI command and return its output.

    All args are passed as separate list elements to subprocess (shell=False),
    so shell metacharacters in user-provided values are treated as literals
    and cannot cause command injection. Path arguments are validated to prevent
    traversal outside the project root.
    """
    # Validate any path-like arguments to prevent directory traversal.
    for arg in args:
        if arg.startswith("-"):
            continue  # flag, not a path
        if ".." in arg.split("/"):
            return json.dumps({"error": f"Invalid argument: path traversal not allowed: {arg}"})

    cmd = ["gco", "--output", "json", *args]
    try:
        result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit - shell=False; args are validated above and passed as literal argv elements
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip() or output
            return json.dumps({"error": error, "exit_code": result.returncode})
        return output if output else json.dumps({"status": "ok"})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Command timed out after 120 seconds"})
    except FileNotFoundError:
        return json.dumps({"error": "gco CLI not found. Install with: pipx install -e ."})
