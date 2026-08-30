"""Dependency-light inventory of canonical Lambda sources and checked-in copies.

This module deliberately imports only the standard library. Deploy packaging,
diagram marker synchronization, and commit-time guards all consume this one map
without forcing code-only tooling to import the AWS CDK stack manager.
"""

from __future__ import annotations

LAMBDA_SHARED_SOURCE_TARGETS: dict[str, tuple[str, ...]] = {
    "lambda/proxy-shared/proxy_utils.py": (
        "lambda/api-gateway-proxy/proxy_utils.py",
        "lambda/regional-api-proxy/proxy_utils.py",
    ),
    "lambda/tls-shared/backend_tls.py": (
        "lambda/proxy-shared/backend_tls.py",
        "lambda/api-gateway-proxy/backend_tls.py",
        "lambda/regional-api-proxy/backend_tls.py",
    ),
}
