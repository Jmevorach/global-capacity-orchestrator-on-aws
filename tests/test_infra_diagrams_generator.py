"""Offline topology contracts for the infrastructure diagram generator."""

from pathlib import Path

import aws_cdk as cdk

from diagrams.infra_diagrams import generate
from gco.config.config_loader import ConfigLoader

ROOT = Path(__file__).resolve().parents[1]


def test_regional_diagram_keeps_helm_convergence_topology(tmp_path: Path, monkeypatch) -> None:
    """Asset stubs must not erase deployable Lambda/Step Functions resources."""
    monkeypatch.chdir(ROOT)
    app = cdk.App(outdir=str(tmp_path / "cdk.out"))
    config = ConfigLoader(app)
    with generate._mocked_regional_assets():
        stack_names = generate._build_regional(app, config)
        assembly = app.synth()

    template = assembly.get_stack_by_name(stack_names[0]).template
    logical_ids = set(template["Resources"])
    required_prefixes = {
        "HelmInstallerFunction",
        "HelmInstallStateMachine",
        "HelmOrchestratorOnEvent",
        "HelmInstallerProvider",
    }
    for prefix in required_prefixes:
        assert any(logical_id.startswith(prefix) for logical_id in logical_ids), prefix


def test_full_architecture_keeps_every_stack_bridge_and_helm_topology(
    tmp_path: Path, monkeypatch
) -> None:
    """Aggregate views must retain stacks and regional convergence resources."""
    monkeypatch.chdir(ROOT)
    app = cdk.App(
        outdir=str(tmp_path / "cdk.out"),
        context=generate._ANALYTICS_CONTEXT,
    )
    config = ConfigLoader(app)
    project = config.get_project_name()
    regions = config.get_deployment_regions()
    with generate._mocked_regional_assets():
        assert generate._build_full(app, config) is None
        assembly = app.synth()

    expected_stacks = {
        f"{project}-global",
        f"{project}-api-gateway",
        f"{project}-monitoring",
        f"{project}-analytics",
        *(f"{project}-{region}" for region in regions["regional"]),
        *(f"{project}-regional-api-{region}" for region in regions["regional"]),
    }
    actual_stacks = {artifact.stack_name for artifact in assembly.stacks}
    assert actual_stacks >= expected_stacks

    required_helm_prefixes = {
        "HelmInstallerFunction",
        "HelmInstallStateMachine",
        "HelmOrchestratorOnEvent",
        "HelmInstallerProvider",
    }
    for region in regions["regional"]:
        regional = assembly.get_stack_by_name(f"{project}-{region}").template
        logical_ids = set(regional["Resources"])
        for prefix in required_helm_prefixes:
            assert any(logical_id.startswith(prefix) for logical_id in logical_ids), (
                region,
                prefix,
            )
        regional_api = assembly.get_stack_by_name(f"{project}-regional-api-{region}").template
        assert any(
            resource["Type"] == "AWS::Lambda::Function"
            for resource in regional_api["Resources"].values()
        ), region
