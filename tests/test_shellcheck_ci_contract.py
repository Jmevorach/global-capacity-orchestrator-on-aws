"""Contract tests for the repository-wide strict ShellCheck CI gate."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LINT_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "lint.yml"
SHELLCHECK_JOB_ID = "lint-shellcheck-shell"
SHELLCHECK_STEP_NAME = "Run strict ShellCheck on every tracked shell script"
PINNED_IMAGE_RE = re.compile(r"koalaman/shellcheck-alpine:v0\.11\.0(?:@sha256:[0-9a-f]{64})?\Z")


def _job() -> dict[str, Any]:
    document = yaml.safe_load(LINT_WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"][SHELLCHECK_JOB_ID]


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, f"expected one {name!r} step, found {len(matches)}"
    return matches[0]


def test_shellcheck_job_identity_and_image_pin_are_stable() -> None:
    """Preserve the required-check name and one exact image source."""
    job = _job()
    assert job["name"] == "lint:shellcheck:shell"
    image = job["env"]["SHELLCHECK_IMAGE"]
    assert PINNED_IMAGE_RE.fullmatch(image), image

    pre_pull = _step(job, "Pre-pull shellcheck image")
    assert pre_pull["uses"] == "./.github/actions/docker-pull-with-retry"
    assert pre_pull["with"]["images"] == "${{ env.SHELLCHECK_IMAGE }}"

    run_script = _step(job, SHELLCHECK_STEP_NAME)["run"]
    assert '"$SHELLCHECK_IMAGE"' in run_script
    assert image not in run_script, "the pinned image must have one source in job.env"


def test_shellcheck_job_is_strict_nul_safe_and_fail_closed() -> None:
    """The workflow must check every tracked shell path without exclusions."""
    script = _step(_job(), SHELLCHECK_STEP_NAME)["run"]

    required_fragments = (
        "set -euo pipefail",
        "git ls-files -z -- '*.sh'",
        '[[ ! -s "$targets" ]]',
        "xargs -0 -r --",
        "--entrypoint /bin/shellcheck",
        '"${PWD}:/repo:ro"',
        "--severity=style",
        "--external-sources",
        '-- < "$targets"',
    )
    for fragment in required_fragments:
        assert fragment in script, f"ShellCheck gate lost required fragment: {fragment}"

    assert "find ." not in script
    assert "-not -path" not in script


def test_tracked_shell_inventory_is_nonempty_and_complete() -> None:
    """The exact Git query used by CI currently discovers all tracked scripts."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.sh"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    paths = [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]

    assert paths, "repository unexpectedly has no tracked shell scripts"
    assert all(path.suffix == ".sh" for path in paths)
    assert Path("demo/record_autopilot.sh") in paths
    assert Path(".github/scripts/dependency-scan.sh") in paths
    assert len(paths) == len(set(paths))
