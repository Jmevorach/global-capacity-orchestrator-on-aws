"""
FastMCP server instance and instructions for the GCO MCP server.

This module creates the shared ``mcp`` FastMCP instance that all tool and
resource modules register against. Import ``mcp`` from here — never create
a second instance.
"""

from fastmcp import FastMCP

mcp = FastMCP(
    "GCO",
    instructions=(
        "Multi-region EKS Auto Mode platform for AI/ML workload orchestration. "
        "Submit jobs, manage inference endpoints, check capacity, track costs, "
        "and manage infrastructure across AWS regions.\n\n"
        "Resources available:\n"
        "- docs:// — Documentation, architecture guides, and example job/inference manifests\n"
        "- k8s:// — Kubernetes manifests deployed to the cluster (RBAC, deployments, NodePools, etc.)\n"
        "- iam:// — IAM policy templates for access control\n"
        "- infra:// — Dockerfiles, Helm charts, CI/CD config\n"
        "- ci:// — GitHub Actions workflows, composite actions, scripts, issue/PR templates\n"
        "- source:// — Full source code of the platform\n"
        "- demos:// — Demo walkthroughs, live demo scripts, and presentation materials\n"
        "- clients:// — API client examples (Python, curl, AWS CLI)\n"
        "- scripts:// — Utility scripts for cluster access, versioning, testing\n"
        "- tests:// — Test suite documentation, patterns, and configuration\n"
        "- config:// — CDK configuration schema, feature toggles, and environment variables\n\n"
        "Start with docs://gco/index or k8s://gco/manifests/index to explore."
    ),
)
