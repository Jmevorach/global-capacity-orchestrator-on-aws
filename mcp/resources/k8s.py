"""Kubernetes manifest resources (k8s:// scheme) for the GCO MCP server."""

from pathlib import Path

from server import mcp

PROJECT_ROOT = Path(__file__).parent.parent.parent
MANIFESTS_DIR = PROJECT_ROOT / "lambda" / "kubectl-applier-simple" / "manifests"


@mcp.resource("k8s://gco/manifests/index")
def k8s_manifests_index() -> str:
    """List all Kubernetes manifests deployed to the EKS cluster."""
    lines = ["# Kubernetes Cluster Manifests\n"]
    lines.append("Applied in order during `gco stacks deploy`:\n")
    for f in sorted(MANIFESTS_DIR.glob("*.yaml")):
        lines.append(f"- `k8s://gco/manifests/{f.name}` — {f.stem}")
    readme = MANIFESTS_DIR / "README.md"
    if readme.is_file():
        lines.append("\n- `k8s://gco/manifests/README.md` — manifest documentation")
    return "\n".join(lines)


@mcp.resource("k8s://gco/manifests/{filename}")
def k8s_manifest_resource(filename: str) -> str:
    """Read a Kubernetes manifest that gets applied to the EKS cluster."""
    path = MANIFESTS_DIR / filename
    if not path.is_file():
        available = sorted(f.name for f in MANIFESTS_DIR.glob("*") if f.is_file())
        return f"Manifest '{filename}' not found. Available:\n" + "\n".join(available)
    return path.read_text()
