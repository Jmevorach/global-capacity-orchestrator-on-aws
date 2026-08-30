"""Dependency-light inference proxy autoscaling defaults and rendering."""

from __future__ import annotations

from collections.abc import Mapping

INFERENCE_PROXY_TLS_CPU_REQUEST_MILLICORES_DEFAULT = 100
INFERENCE_PROXY_TLS_CPU_TARGET_UTILIZATION_DEFAULT = 70


def compute_inference_proxy_tls_replacements(
    config: Mapping[str, object],
) -> dict[str, str]:
    """Render typed TLS CPU placeholders without importing AWS CDK."""
    request = config["tls_proxy_cpu_request_millicores"]
    target = config["tls_proxy_cpu_target_utilization_percentage"]
    if type(request) is not int or type(target) is not int:
        raise ValueError("validated inference proxy TLS settings must be integers")
    return {
        "{{INFERENCE_PROXY_TLS_CPU_REQUEST}}": f"{request}m",
        "{{INFERENCE_PROXY_TLS_CPU_TARGET_UTILIZATION}}": str(target),
    }
