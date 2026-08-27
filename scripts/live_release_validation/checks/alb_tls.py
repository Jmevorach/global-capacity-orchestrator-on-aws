"""Live ELBv2 evidence for the TLS-only GCO Gateway data path."""

from __future__ import annotations

import json
import time
from typing import Any

from gco.stacks.constants import backend_tls_certificate_arn_parameter_name

from ..models import RunContext, utc_now

_GATEWAY_TAG = "gco.aws/gateway"
_GATEWAY_TAG_VALUE = "gco-system/gco-gateway"
_CLUSTER_TAG = "elbv2.k8s.aws/cluster"
_TARGET_CONVERGENCE_TIMEOUT_SECONDS = 5 * 60


def _ssm_string_parameter(client: Any, name: str) -> str:
    response = client.get_parameter(Name=name)
    parameter = response.get("Parameter") if isinstance(response, dict) else None
    if not isinstance(parameter, dict):
        raise RuntimeError(f"SSM parameter response is malformed for {name}")
    if parameter.get("Name") != name or parameter.get("Type") != "String":
        raise RuntimeError(f"SSM parameter identity/type is invalid for {name}")
    value = parameter.get("Value")
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"SSM parameter has no String value: {name}")
    return value


def _alb_https_target_evidence(
    ctx: RunContext,
    *,
    region: str,
    cluster_name: str,
) -> dict[str, Any]:
    """Require the exact HTTPS listener, certificate, target groups, and health."""
    client = ctx.session.client("elbv2", region_name=region)
    load_balancers: list[dict[str, Any]] = []
    for page in client.get_paginator("describe_load_balancers").paginate():
        load_balancers.extend(page.get("LoadBalancers", []))

    tags_by_arn: dict[str, dict[str, str]] = {}
    for start in range(0, len(load_balancers), 20):
        arns = [
            str(item.get("LoadBalancerArn") or "") for item in load_balancers[start : start + 20]
        ]
        if not all(arns):
            raise RuntimeError(f"ELBv2 returned a load balancer without an ARN in {region}")
        for description in client.describe_tags(ResourceArns=arns).get("TagDescriptions", []):
            arn = str(description.get("ResourceArn") or "")
            tags_by_arn[arn] = {
                str(tag.get("Key") or ""): str(tag.get("Value") or "")
                for tag in description.get("Tags", [])
            }

    matches = []
    for load_balancer in load_balancers:
        arn = str(load_balancer.get("LoadBalancerArn") or "")
        tags = tags_by_arn.get(arn, {})
        if tags.get(_GATEWAY_TAG) == _GATEWAY_TAG_VALUE and tags.get(_CLUSTER_TAG) == cluster_name:
            matches.append(load_balancer)
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one owned GCO Gateway ALB in {region}; found {len(matches)}"
        )

    load_balancer = matches[0]
    load_balancer_arn = str(load_balancer.get("LoadBalancerArn") or "")
    if load_balancer.get("Scheme") != "internal" or load_balancer.get("Type") != "application":
        raise RuntimeError(f"GCO Gateway load balancer has an invalid type or scheme in {region}")
    if (load_balancer.get("State") or {}).get("Code") != "active":
        raise RuntimeError(f"GCO Gateway load balancer is not active in {region}")

    certificate_parameter = backend_tls_certificate_arn_parameter_name(
        ctx.config.project_name,
        region,
    )
    expected_certificate_arn = _ssm_string_parameter(
        ctx.session.client("ssm", region_name=ctx.config.global_region),
        certificate_parameter,
    )
    listeners: list[dict[str, Any]] = []
    for page in client.get_paginator("describe_listeners").paginate(
        LoadBalancerArn=load_balancer_arn
    ):
        listeners.extend(page.get("Listeners", []))
    if len(listeners) != 1:
        raise RuntimeError(
            f"GCO Gateway ALB in {region} has {len(listeners)} listeners; expected exactly 1"
        )
    listener = listeners[0]
    listener_arn = str(listener.get("ListenerArn") or "")
    if not listener_arn:
        raise RuntimeError(f"GCO Gateway listener in {region} has no ARN")
    default_certificates = {
        str(item.get("CertificateArn") or "") for item in listener.get("Certificates", [])
    }
    certificate_descriptions: list[dict[str, Any]] = []
    for page in client.get_paginator("describe_listener_certificates").paginate(
        ListenerArn=listener_arn
    ):
        certificate_descriptions.extend(page.get("Certificates", []))
    listener_certificates = {
        str(item.get("CertificateArn") or "") for item in certificate_descriptions
    }
    default_listener_certificates = {
        str(item.get("CertificateArn") or "")
        for item in certificate_descriptions
        if item.get("IsDefault") is True
    }
    expected_listener = {
        "Protocol": "HTTPS",
        "Port": 443,
        "SslPolicy": "ELBSecurityPolicy-TLS13-1-2-2021-06",
    }
    listener_mismatches = {
        field: {"expected": value, "actual": listener.get(field)}
        for field, value in expected_listener.items()
        if listener.get(field) != value
    }
    if default_certificates != {expected_certificate_arn}:
        listener_mismatches["DefaultCertificate"] = {
            "expected": [expected_certificate_arn],
            "actual": sorted(default_certificates),
        }
    if listener_certificates != {expected_certificate_arn} or default_listener_certificates != {
        expected_certificate_arn
    }:
        listener_mismatches["ListenerCertificates"] = {
            "expected": [{"arn": expected_certificate_arn, "is_default": True}],
            "actual": sorted(
                (
                    {
                        "arn": str(item.get("CertificateArn") or ""),
                        "is_default": item.get("IsDefault") is True,
                    }
                    for item in certificate_descriptions
                ),
                key=lambda item: item["arn"],
            ),
        }
    if listener_mismatches:
        raise RuntimeError(
            f"GCO Gateway listener in {region} is not the exact HTTPS-only contract: "
            f"{json.dumps(listener_mismatches, sort_keys=True)}"
        )

    target_groups: list[dict[str, Any]] = []
    for page in client.get_paginator("describe_target_groups").paginate(
        LoadBalancerArn=load_balancer_arn
    ):
        target_groups.extend(page.get("TargetGroups", []))
    if len(target_groups) < 3:
        raise RuntimeError(
            f"GCO Gateway ALB in {region} has {len(target_groups)} target groups; expected at least 3"
        )

    evidence: dict[str, Any] = {
        "region": region,
        "cluster_name": cluster_name,
        "load_balancer_arn": load_balancer_arn,
        "scheme": load_balancer.get("Scheme"),
        "state": (load_balancer.get("State") or {}).get("Code"),
        "listener": {
            "listener_arn": listener.get("ListenerArn"),
            "protocol": listener.get("Protocol"),
            "port": listener.get("Port"),
            "ssl_policy": listener.get("SslPolicy"),
            "certificates": sorted(listener_certificates),
            "default_certificates": sorted(default_listener_certificates),
        },
        "target_groups": [],
    }
    state = ctx.checkpoint.state.setdefault("topology_alb_https_targets", {})
    state[region] = evidence
    ctx.persist()

    poll_seconds = max(1.0, float(ctx.settings.poll_interval_seconds))
    for target_group in sorted(
        target_groups,
        key=lambda item: str(item.get("TargetGroupArn") or ""),
    ):
        arn = str(target_group.get("TargetGroupArn") or "")
        if not arn:
            raise RuntimeError(f"ELBv2 returned a target group without an ARN in {region}")
        expected = {
            "Protocol": "HTTPS",
            "Port": 8443,
            "HealthCheckProtocol": "HTTPS",
            "TargetType": "ip",
            "HealthCheckPath": "/healthz",
        }
        mismatches = {
            field: {"expected": value, "actual": target_group.get(field)}
            for field, value in expected.items()
            if target_group.get(field) != value
        }
        if mismatches:
            raise RuntimeError(
                f"GCO Gateway target group {arn} is not HTTPS-hardened: "
                f"{json.dumps(mismatches, sort_keys=True)}"
            )

        group_evidence: dict[str, Any] = {
            "target_group_arn": arn,
            "port": target_group.get("Port"),
            "protocol": target_group.get("Protocol"),
            "health_check_protocol": target_group.get("HealthCheckProtocol"),
            "health_check_path": target_group.get("HealthCheckPath"),
            "target_type": target_group.get("TargetType"),
            "health_observations": [],
        }
        evidence["target_groups"].append(group_evidence)
        deadline = time.monotonic() + _TARGET_CONVERGENCE_TIMEOUT_SECONDS
        while True:
            health_response = client.describe_target_health(TargetGroupArn=arn)
            descriptions = health_response.get("TargetHealthDescriptions", [])
            states = [
                str((item.get("TargetHealth") or {}).get("State") or "") for item in descriptions
            ]
            observation = {
                "observed_at": utc_now(),
                "states": states,
                "reasons": [
                    str((item.get("TargetHealth") or {}).get("Reason") or "")
                    for item in descriptions
                ],
            }
            group_evidence["health_observations"].append(observation)
            group_evidence["target_states"] = states
            ctx.persist()

            invalid_states = sorted(
                {
                    state_value
                    for state_value in states
                    if state_value not in {"healthy", "draining"}
                }
            )
            if descriptions and "healthy" in states and not invalid_states:
                break
            terminal_states = sorted(
                {
                    state_value
                    for state_value in invalid_states
                    if state_value not in {"initial", "unused", "unavailable"}
                }
            )
            if terminal_states:
                raise RuntimeError(
                    f"GCO Gateway target group {arn} has nonhealthy targets: {terminal_states}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"GCO Gateway target group {arn} did not acquire healthy HTTPS targets "
                    f"within {_TARGET_CONVERGENCE_TIMEOUT_SECONDS} seconds; states={states}"
                )
            time.sleep(min(poll_seconds, remaining))

    return evidence
