"""Job management MCP tools."""

from audit import audit_logged
import cli_runner
from server import mcp


@mcp.tool()
@audit_logged
def list_jobs(
    region: str | None = None, namespace: str | None = None, status: str | None = None
) -> str:
    """List jobs across GCO clusters.

    Args:
        region: AWS region (e.g. us-east-1). If omitted, lists across all regions.
        namespace: Filter by Kubernetes namespace.
        status: Filter by job status (pending, running, completed, succeeded, failed).
    """
    args = ["jobs", "list"]
    if region:
        args += ["-r", region]
    else:
        args += ["--all-regions"]
    if namespace:
        args += ["-n", namespace]
    if status:
        args += ["-s", status]
    return cli_runner._run_cli(*args)


@mcp.tool()
@audit_logged
def submit_job_sqs(
    manifest_path: str, region: str, namespace: str | None = None, priority: int | None = None
) -> str:
    """Submit a job via SQS queue (recommended for production).

    Args:
        manifest_path: Path to the YAML manifest file (relative to project root).
        region: Target AWS region for the SQS queue.
        namespace: Override the namespace in the manifest.
        priority: Job priority (0-100, higher = more important).
    """
    args = ["jobs", "submit-sqs", manifest_path, "-r", region]
    if namespace:
        args += ["-n", namespace]
    if priority is not None:
        args += ["--priority", str(priority)]
    return cli_runner._run_cli(*args)


@mcp.tool()
@audit_logged
def submit_job_api(manifest_path: str, namespace: str | None = None) -> str:
    """Submit a job via the authenticated API Gateway (SigV4).

    Args:
        manifest_path: Path to the YAML manifest file.
        namespace: Override the namespace in the manifest.
    """
    args = ["jobs", "submit", manifest_path]
    if namespace:
        args += ["-n", namespace]
    return cli_runner._run_cli(*args)


@mcp.tool()
@audit_logged
def get_job(job_name: str, region: str, namespace: str = "gco-jobs") -> str:
    """Get details of a specific job.

    Args:
        job_name: Name of the job.
        region: AWS region where the job is running.
        namespace: Kubernetes namespace.
    """
    return cli_runner._run_cli("jobs", "get", job_name, "-r", region, "-n", namespace)


@mcp.tool()
@audit_logged
def get_job_logs(job_name: str, region: str, namespace: str = "gco-jobs", tail: int = 100) -> str:
    """Get logs from a job.

    Args:
        job_name: Name of the job.
        region: AWS region.
        namespace: Kubernetes namespace.
        tail: Number of log lines to return.
    """
    return cli_runner._run_cli("jobs", "logs", job_name, "-r", region, "-n", namespace, "--tail", str(tail))


@mcp.tool()
@audit_logged
def delete_job(job_name: str, region: str, namespace: str = "gco-jobs") -> str:
    """Delete a job.

    Args:
        job_name: Name of the job to delete.
        region: AWS region.
        namespace: Kubernetes namespace.
    """
    return cli_runner._run_cli("jobs", "delete", job_name, "-r", region, "-n", namespace, "-y")


@mcp.tool()
@audit_logged
def get_job_events(job_name: str, region: str, namespace: str = "gco-jobs") -> str:
    """Get Kubernetes events for a job (useful for debugging).

    Args:
        job_name: Name of the job.
        region: AWS region.
        namespace: Kubernetes namespace.
    """
    return cli_runner._run_cli("jobs", "events", job_name, "-r", region, "-n", namespace)


@mcp.tool()
@audit_logged
def cluster_health(region: str | None = None) -> str:
    """Get health status of GCO clusters.

    Args:
        region: Specific region, or omit for all regions.
    """
    args = ["jobs", "health"]
    if region:
        args += ["-r", region]
    else:
        args += ["--all-regions"]
    return cli_runner._run_cli(*args)


@mcp.tool()
@audit_logged
def queue_status(region: str | None = None) -> str:
    """View SQS queue status (pending, in-flight, DLQ counts).

    Args:
        region: Specific region, or omit for all regions.
    """
    args = ["jobs", "queue-status"]
    if region:
        args += ["-r", region]
    else:
        args += ["--all-regions"]
    return cli_runner._run_cli(*args)
