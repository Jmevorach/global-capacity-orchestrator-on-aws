"""Strict immutable runtime contracts for the live inference matrix."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from cli._image_reference import immutable_sha256_digest

Framework = Literal["vllm", "tgi"]

INFERENCE_OWNER_LABEL = "gco-managed-inference-validation-owner"
INFERENCE_CONTRACT_VERSION = 2
_FRAMEWORK_ORDER: tuple[Framework, ...] = ("vllm", "tgi")
_DEFAULT_PORTS: dict[Framework, int] = {"vllm": 8000, "tgi": 8080}
_DEFAULT_REQUEST_PATHS: dict[Framework, str] = {
    "vllm": "/v1/completions",
    "tgi": "/generate",
}
_RESPONSE_CONTRACTS: dict[Framework, str] = {
    "vllm": "choices[0].text:non-empty-string",
    "tgi": "generated_text:non-empty-string",
}
_MODEL_INFO_PATHS: dict[Framework, str] = {
    "vllm": "/v1/models",
    "tgi": "/info",
}


@dataclass(frozen=True)
class InferenceRuntimeSpec:
    """One digest-pinned server and immutable model revision."""

    framework: Framework
    image: str
    model_id: str
    model_revision: str
    port: int

    @property
    def request_path(self) -> str:
        return _DEFAULT_REQUEST_PATHS[self.framework]

    @property
    def model_info_path(self) -> str:
        return _MODEL_INFO_PATHS[self.framework]


def _plain_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_runtime(runtime: InferenceRuntimeSpec) -> None:
    if runtime.framework not in _FRAMEWORK_ORDER:
        raise ValueError("inference runtime framework must be 'vllm' or 'tgi'")
    if immutable_sha256_digest(runtime.image) is None:
        raise ValueError(
            f"{runtime.framework} image must be an immutable lowercase @sha256: reference"
        )
    if not runtime.model_id.strip() or runtime.model_id != runtime.model_id.strip():
        raise ValueError(f"{runtime.framework} model_id must be a non-empty trimmed value")
    if not re.fullmatch(r"[0-9a-f]{40}", runtime.model_revision):
        raise ValueError(
            f"{runtime.framework} model_revision must be a full lowercase 40-hex commit"
        )
    if runtime.port != _DEFAULT_PORTS[runtime.framework]:
        raise ValueError(
            f"{runtime.framework} live validation port must be {_DEFAULT_PORTS[runtime.framework]}"
        )


def validate_inference_settings(settings: Any) -> None:
    """Validate every run-level and per-runtime inference input."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", settings.selected_region):
        raise ValueError("selected_region must be a lowercase AWS Region name")
    runtimes = settings.inference_runtimes
    if not isinstance(runtimes, tuple) or tuple(runtime.framework for runtime in runtimes) != (
        "vllm",
        "tgi",
    ):
        raise ValueError("managed inference validation requires vLLM then TGI runtime specs")
    for runtime in runtimes:
        _validate_runtime(runtime)
    image_digests = [runtime.image.rsplit("@sha256:", 1)[1] for runtime in runtimes]
    if len(set(image_digests)) != len(image_digests):
        raise ValueError("vLLM and TGI runtime images must have distinct immutable digests")
    if not settings.request_prompt.strip():
        raise ValueError("request_prompt must be non-empty")
    if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?", settings.namespace):
        raise ValueError("namespace must be a DNS-safe Kubernetes name")
    if (
        not isinstance(settings.gpu_count, int)
        or isinstance(settings.gpu_count, bool)
        or settings.gpu_count < 0
    ):
        raise ValueError("gpu_count must be a non-negative integer")
    for field_name in (
        "request_max_tokens",
        "baseline_replicas",
        "autoscale_initial_replicas",
        "hpa_min_replicas",
        "hpa_max_replicas",
        "endpoint_count",
        "command_timeout_seconds",
        "readiness_timeout_seconds",
        "hpa_timeout_seconds",
        "deletion_timeout_seconds",
        "monitor_interval_seconds",
        "hpa_stability_intervals",
        "job_timeout_seconds",
        "queue_timeout_seconds",
        "poll_interval_seconds",
        "destroy_attempts",
        "destroy_retry_delay_seconds",
    ):
        if not _plain_positive_int(getattr(settings, field_name)):
            raise ValueError(f"{field_name} must be a positive integer")
    if settings.endpoint_count != 4:
        raise ValueError("managed inference validation requires exactly four endpoints")
    if settings.baseline_replicas != 1 or settings.autoscale_initial_replicas != 1:
        raise ValueError("all managed inference endpoints must start with one replica")
    if settings.hpa_min_replicas != 2 or settings.hpa_max_replicas != 2:
        raise ValueError("the CPU HPA validation requires min_replicas=max_replicas=2")
    if not isinstance(settings.hpa_cpu_target, int) or isinstance(settings.hpa_cpu_target, bool):
        raise ValueError("hpa_cpu_target must be an integer")
    if not 1 <= settings.hpa_cpu_target <= 100:
        raise ValueError("hpa_cpu_target must be from 1 through 100")
    if settings.hpa_stability_intervals < 2:
        raise ValueError("hpa_stability_intervals must be at least two")
    if settings.health_path != "/health":
        raise ValueError("managed inference validation requires the official /health path")
    if not re.fullmatch(r"[1-9][0-9]*m", settings.proxy_tls_cpu_request):
        raise ValueError("proxy_tls_cpu_request must be a positive millicore quantity")
    if (
        not isinstance(settings.proxy_tls_cpu_target, int)
        or isinstance(settings.proxy_tls_cpu_target, bool)
        or not 1 <= settings.proxy_tls_cpu_target <= 100
    ):
        raise ValueError("proxy_tls_cpu_target must be an integer from 1 through 100")
    if not settings.consent:
        raise ValueError("explicit managed inference deployment/destruction consent is required")


def inference_request_body(settings: Any, runtime: InferenceRuntimeSpec) -> dict[str, Any]:
    """Return the deterministic request body for one exact framework adapter."""
    if runtime.framework == "tgi":
        return {
            "inputs": settings.request_prompt,
            "parameters": {
                "do_sample": False,
                "max_new_tokens": settings.request_max_tokens,
            },
        }
    return {
        "max_tokens": settings.request_max_tokens,
        "model": runtime.model_id,
        "prompt": settings.request_prompt,
        "stream": False,
        "temperature": 0,
    }


def inference_framework_env(runtime: InferenceRuntimeSpec) -> dict[str, str]:
    """Return only official launcher environment for the selected runtime."""
    if runtime.framework == "tgi":
        return {
            "MODEL_ID": runtime.model_id,
            "PORT": str(runtime.port),
            "REVISION": runtime.model_revision,
        }
    return {"MODEL": runtime.model_id}


def inference_deploy_extra_args(runtime: InferenceRuntimeSpec) -> tuple[str, ...]:
    """Return official immutable-model arguments for the selected runtime."""
    if runtime.framework == "vllm":
        return (
            "--model",
            runtime.model_id,
            "--revision",
            runtime.model_revision,
        )
    return ()


def _runtime_identity(settings: Any, runtime: InferenceRuntimeSpec) -> dict[str, Any]:
    return {
        "framework": runtime.framework,
        "image": runtime.image,
        "model": {"id": runtime.model_id, "revision": runtime.model_revision},
        "server": {
            "port": runtime.port,
            "health_path": settings.health_path,
        },
        "request_contract": {
            "path": runtime.request_path,
            "body": inference_request_body(settings, runtime),
            "response": _RESPONSE_CONTRACTS[runtime.framework],
        },
        "probe_contract": {
            "health_path": settings.health_path,
            "model_info_path": runtime.model_info_path,
            "expected_model_id": runtime.model_id,
            "expected_model_revision": runtime.model_revision,
        },
        "deploy_contract": {
            "framework_env": inference_framework_env(runtime),
            "extra_args": list(inference_deploy_extra_args(runtime)),
        },
    }


def inference_identity_fields(settings: Any) -> dict[str, Any]:
    """Return every inference input that must match on resume."""
    return {
        "contract_version": INFERENCE_CONTRACT_VERSION,
        "selected_region": settings.selected_region,
        "runtimes": [
            _runtime_identity(settings, runtime) for runtime in settings.inference_runtimes
        ],
        "endpoint_contract": {
            "count": settings.endpoint_count,
            "namespace": settings.namespace,
            "gpu_count": settings.gpu_count,
            "accelerator": "nvidia",
            "rewrite_image": False,
            "roles_per_runtime": ["baseline", "hpa"],
            "baseline_replicas": settings.baseline_replicas,
            "autoscale_initial_replicas": settings.autoscale_initial_replicas,
            "hpa": {
                "metric": "cpu",
                "target": settings.hpa_cpu_target,
                "min_replicas": settings.hpa_min_replicas,
                "max_replicas": settings.hpa_max_replicas,
            },
        },
        "shared_proxy_contract": {
            "namespace": "gco-system",
            "deployment": "inference-proxy",
            "hpa": "inference-proxy-hpa",
            "tls_container": "api-tls-proxy",
            "tls_cpu_request": settings.proxy_tls_cpu_request,
            "tls_cpu_target": settings.proxy_tls_cpu_target,
            "metric_type": "ContainerResource",
        },
        "timeouts": {
            "command_seconds": settings.command_timeout_seconds,
            "readiness_seconds": settings.readiness_timeout_seconds,
            "hpa_seconds": settings.hpa_timeout_seconds,
            "deletion_seconds": settings.deletion_timeout_seconds,
            "poll_seconds": settings.poll_interval_seconds,
            "monitor_interval_seconds": settings.monitor_interval_seconds,
            "hpa_stability_intervals": settings.hpa_stability_intervals,
            "job_seconds": settings.job_timeout_seconds,
            "queue_seconds": settings.queue_timeout_seconds,
            "destroy_attempts": settings.destroy_attempts,
            "destroy_retry_delay_seconds": settings.destroy_retry_delay_seconds,
        },
        "consent": settings.consent,
    }
