"""Infrastructure stack management MCP tools."""

from audit import audit_logged
import cli_runner
from server import mcp


@mcp.tool()
@audit_logged
def list_stacks() -> str:
    """List all GCO CDK stacks."""
    return cli_runner._run_cli("stacks", "list")


@mcp.tool()
@audit_logged
def stack_status(stack_name: str, region: str) -> str:
    """Get detailed status of a CloudFormation stack.

    Args:
        stack_name: Stack name (e.g. gco-us-east-1).
        region: AWS region.
    """
    return cli_runner._run_cli("stacks", "status", stack_name, "-r", region)


@mcp.tool()
@audit_logged
def setup_cluster_access(cluster: str | None = None, region: str | None = None) -> str:
    """Configure kubectl access to a GCO EKS cluster.

    Updates kubeconfig, creates an EKS access entry for your IAM principal,
    and associates the cluster admin policy. Handles assumed roles automatically.

    Args:
        cluster: Cluster name (default: gco-{region}).
        region: AWS region (default: first deployment region from cdk.json).
    """
    args = ["stacks", "access"]
    if cluster:
        args.extend(["-c", cluster])
    if region:
        args.extend(["-r", region])
    return cli_runner._run_cli(*args)


@mcp.tool()
@audit_logged
def fsx_status() -> str:
    """Check FSx for Lustre configuration status."""
    return cli_runner._run_cli("stacks", "fsx", "status")
