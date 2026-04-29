"""Pinned version constants for GCO infrastructure.

Single source of truth for all version-pinned infrastructure components.
Centralising these makes it easy to:

1. See every pinned version at a glance
2. Update versions in one place
3. Let the dependency scanner (`.github/scripts/dependency-scan.sh`)
   find them with a simple import instead of regex scraping
4. Write tests that assert versions haven't drifted

When updating a version here, also check:
- ``lambda/helm-installer/charts.yaml`` for Helm chart versions
- ``requirements-lock.txt`` for Python dependency versions
- ``cdk.json`` context for ``kubernetes_version``

The dependency scanner runs monthly and opens an issue when any of
these fall behind the latest available release.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Lambda Runtime
# ---------------------------------------------------------------------------
# All Lambda functions in GCO use the same Python runtime. Changing this
# single constant updates every function across all stacks.
LAMBDA_PYTHON_RUNTIME = "PYTHON_3_14"
"""CDK enum name for the Lambda runtime (e.g. ``lambda_.Runtime.PYTHON_3_14``)."""

# ---------------------------------------------------------------------------
# EKS Add-on Versions
# ---------------------------------------------------------------------------
# Pinned to specific eksbuild versions for reproducible deployments.
# The dependency scanner checks ``aws eks describe-addon-versions`` monthly
# and opens an issue when newer builds are available.

EKS_ADDON_POD_IDENTITY_AGENT = "v1.3.10-eksbuild.3"
"""EKS Pod Identity Agent — enables IRSA and Pod Identity for service accounts."""

EKS_ADDON_METRICS_SERVER = "v0.8.1-eksbuild.6"
"""Kubernetes Metrics Server — provides CPU/memory metrics for HPA and ``kubectl top``."""

EKS_ADDON_EFS_CSI_DRIVER = "v3.0.1-eksbuild.1"
"""Amazon EFS CSI Driver — mounts EFS file systems as Kubernetes persistent volumes."""

EKS_ADDON_CLOUDWATCH_OBSERVABILITY = "v5.3.1-eksbuild.1"
"""Amazon CloudWatch Observability — Container Insights, Prometheus metrics, FluentBit logs."""

EKS_ADDON_FSX_CSI_DRIVER = "v1.8.0-eksbuild.2"
"""Amazon FSx CSI Driver — mounts FSx for Lustre file systems as Kubernetes persistent volumes."""

# ---------------------------------------------------------------------------
# Aurora PostgreSQL Engine Version
# ---------------------------------------------------------------------------
# Pinned to a specific minor version. The dependency scanner checks
# ``aws rds describe-db-engine-versions`` monthly for newer releases
# within the same major line.

AURORA_POSTGRES_VERSION = "VER_17_9"
"""CDK enum name for the Aurora PostgreSQL engine version (e.g. ``rds.AuroraPostgresEngineVersion.VER_17_9``)."""

AURORA_POSTGRES_VERSION_DISPLAY = "17.9"
"""Human-readable version string for documentation and logging."""
