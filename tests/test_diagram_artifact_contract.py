"""Structural contracts for committed code and infrastructure diagrams."""

import subprocess
import sys
from pathlib import Path

from PIL import Image

from diagrams.code_diagrams._targets import TARGETS
from diagrams.generate import _marker_pointer_issues, check_diagram_contract
from diagrams.infra_diagrams._catalog import INFRA_DIAGRAM_NAMES

ROOT = Path(__file__).resolve().parents[1]

_REQUIRED_HIGH_VALUE_TARGETS = {
    ("lambda/capacity-poller/handler.py", "lambda_handler"),
    ("lambda/helm-orchestrator/handler.py", "on_event"),
    ("lambda/traffic-dial-controller/handler.py", "lambda_handler"),
    ("gco/services/spot_price_gate.py", "SpotPriceGate.evaluate"),
    ("cli/commands/autopilot_cmd.py", "_plan"),
    ("gco_mcp/mission/swarm_runner.py", "SwarmRunner.run_to_completion"),
    (
        "gco/services/request_size_middleware.py",
        "RequestSizeLimitMiddleware.__call__",
    ),
    ("gco/services/webhook_dispatcher.py", "WebhookDispatcher._deliver_webhook"),
    ("gco/services/mooncake_pd_proxy.py", "_dispatch"),
    ("gco/services/health_monitor.py", "HealthMonitor.get_health_status"),
    (
        "gco/services/inference_monitor.py",
        "InferenceMonitor._reconcile_endpoint_authorized",
    ),
}


def test_committed_diagram_catalogues_are_structurally_current() -> None:
    """Targets, artifacts, indexes, timestamps, and markers move together."""
    assert check_diagram_contract(ROOT) == []


def test_code_only_check_has_no_cdk_or_site_package_dependency() -> None:
    result = subprocess.run(
        [sys.executable, "-S", "diagrams/generate.py", "--check", "--code-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Diagram artifact contract is current"


def test_source_marker_contract_rejects_wrong_or_missing_artifact_pointers() -> None:
    source = """# <pyflowchart-code-diagram> BEGIN - auto-inserted, do not edit
# Generated at (UTC): 2026-08-30T12:00:00Z
# Generated from Git commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
# Flowchart(s) generated from this file:
#   * ``Thing.run`` -> ``diagrams/code_diagrams/thing.Thing_run.html``
#     (PNG: ``diagrams/code_diagrams/thing.Thing_run.png``)
# Regenerate with ``SOURCE_DATE_EPOCH=<unix-seconds> GCO_DIAGRAM_SOURCE_COMMIT=<40-char-sha> python diagrams/generate.py --code-only``.
# <pyflowchart-code-diagram> END
"""
    expected = {
        (
            "Thing.run",
            "diagrams/code_diagrams/thing.Thing_run.html",
            "diagrams/code_diagrams/thing.Thing_run.png",
        )
    }
    assert _marker_pointer_issues(source, expected, "thing.py") == []
    assert _marker_pointer_issues(
        source.replace("thing.Thing_run.html", "thing.stale.html"),
        expected,
        "thing.py",
    )
    assert _marker_pointer_issues(
        source.replace(
            "#     (PNG: ``diagrams/code_diagrams/thing.Thing_run.png``)\n",
            "",
        ),
        expected,
        "thing.py",
    )
    begin = "# <pyflowchart-code-diagram> BEGIN - auto-inserted, do not edit\n"
    end = "# <pyflowchart-code-diagram> END\n"
    assert _marker_pointer_issues(source.replace(begin, begin + begin, 1), expected, "thing.py")
    assert _marker_pointer_issues(source + end, expected, "thing.py")
    assert _marker_pointer_issues(
        source.replace(
            "# Flowchart(s) generated from this file:\n",
            "# Flowchart(s) generated from this file:\n# unexpected marker content\n",
        ),
        expected,
        "thing.py",
    )


def test_required_high_value_code_flows_remain_catalogued() -> None:
    catalog = {(target.source, target.function) for target in TARGETS}
    assert catalog >= _REQUIRED_HIGH_VALUE_TARGETS


def test_committed_pngs_are_valid_with_nonzero_dimensions() -> None:
    """Pillow must parse and verify every committed generated PNG."""
    paths = sorted((ROOT / "diagrams" / "code_diagrams").rglob("*.png"))
    paths += sorted((ROOT / "diagrams" / "infra_diagrams").glob("*.png"))
    assert len(paths) == len(TARGETS) + len(INFRA_DIAGRAM_NAMES)

    # Whole-architecture views are intentionally large. Disable Pillow's
    # generic web-upload bomb heuristic for these trusted local artifacts;
    # verify() streams and CRC-checks PNG chunks without allocating a full
    # multi-hundred-megapixel pixel buffer.
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None
    try:
        for path in paths:
            assert path.stat().st_size > 0, path
            with Image.open(path) as image:
                assert image.format == "PNG", path
                assert image.width > 0 and image.height > 0, path
                image.verify()
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


def test_infrastructure_catalog_has_six_stack_and_two_aggregate_views() -> None:
    assert INFRA_DIAGRAM_NAMES == (
        "global-stack",
        "api-gateway-stack",
        "regional-stack",
        "regional-api-stack",
        "monitoring-stack",
        "analytics-stack",
        "full-architecture",
        "full-architecture-detailed",
    )
