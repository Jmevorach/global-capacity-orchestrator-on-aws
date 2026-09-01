#!/usr/bin/env python3
"""Generate code flowcharts for GCO using pyflowchart + Playwright.

For each ``(source_file, function)`` target in :data:`TARGETS`:

1. Parse the function body with :mod:`pyflowchart` to produce a
   flowchart.js DSL string.
2. Emit an interactive HTML page (flowchart.js renders client-side).
3. Render the same diagram to a PNG using a headless Chromium via
   :mod:`playwright` (optional — when skipped or unavailable, any older PNG
   for that target is removed so artifact timestamps cannot disagree).
4. Stamp the HTML, PNG, generated catalogue, and source marker with one
   invocation-wide UTC generation time.
5. Insert (idempotently) a source comment near the top of the source file
   pointing at the generated HTML and PNG.

Outputs mirror the source tree under ``diagrams/code_diagrams/``:

    lambda/analytics-presigned-url/handler.py::lambda_handler
        -> diagrams/code_diagrams/lambda/analytics-presigned-url/handler.lambda_handler.{html,png}

The README in ``diagrams/code_diagrams/`` is regenerated at the end
with a hierarchical, grouped-by-top-level-directory index so the
listing reflects the actual project layout.

Usage:
    GCO_DIAGRAM_SOURCE_COMMIT=<40-char-sha> python diagrams/code_diagrams/generate.py
    GCO_DIAGRAM_SOURCE_COMMIT=<40-char-sha> python diagrams/code_diagrams/generate.py --target lambda/analytics-presigned-url/handler.py:lambda_handler
    GCO_DIAGRAM_SOURCE_COMMIT=<40-char-sha> python diagrams/code_diagrams/generate.py --skip-png
    GCO_DIAGRAM_SOURCE_COMMIT=<40-char-sha> python diagrams/code_diagrams/generate.py --skip-marker
    python diagrams/code_diagrams/generate.py --strip-markers
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Add project root to path so direct script invocation works without a prior
# ``pip install -e .``. The project root is two parents up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from diagrams.code_diagrams._renderer import (  # noqa: E402
    prune_orphaned_artifacts,
    render_all,
    write_readme,
)
from diagrams.code_diagrams._source_marker import (  # noqa: E402
    SENTINEL,
    strip_all_markers,
    upsert_markers,
)
from diagrams.code_diagrams._targets import TARGETS, Target  # noqa: E402
from diagrams.code_diagrams._timestamp import (  # noqa: E402
    generation_source_commit,
    generation_timestamp_utc,
)
from gco.lambda_shared_sources import LAMBDA_SHARED_SOURCE_TARGETS  # noqa: E402

_MARKER_BYTES_RE = re.compile(
    rb"(?:\r?\n)?# <" + re.escape(SENTINEL.encode()) + rb"> BEGIN[^\r\n]*\r?\n.*?"
    rb"# <" + re.escape(SENTINEL.encode()) + rb"> END(?:\r?\n){2}",
    re.DOTALL,
)


def _without_generated_marker(source: bytes) -> bytes:
    """Remove only the generated marker bytes; preserve every other byte."""
    return _MARKER_BYTES_RE.sub(b"", source)


def _verify_targets_match_source_commit(
    *, project_root: Path, targets: list[Target], source_commit: str
) -> None:
    """Require marker-excluded target bytes to equal a real Git commit."""
    object_type = subprocess.run(  # noqa: S603 — fixed Git command, hex-only ref
        ["git", "cat-file", "-t", source_commit],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    if object_type.returncode != 0:
        detail = object_type.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"GCO_DIAGRAM_SOURCE_COMMIT {source_commit} does not resolve: {detail}")
    if object_type.stdout.strip() != b"commit":
        actual_type = object_type.stdout.decode(errors="replace").strip()
        raise RuntimeError(
            f"GCO_DIAGRAM_SOURCE_COMMIT {source_commit} is a {actual_type}, not a commit"
        )

    mismatches: list[str] = []
    for source in sorted({target.source for target in targets}):
        result = subprocess.run(  # noqa: S603 — fixed Git command and catalog paths
            ["git", "show", f"{source_commit}:{source}"],
            cwd=project_root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(
                f"cannot read {source} from GCO_DIAGRAM_SOURCE_COMMIT {source_commit}: {detail}"
            )
        current = (project_root / source).read_bytes()
        if _without_generated_marker(current) != _without_generated_marker(result.stdout):
            mismatches.append(source)
    if mismatches:
        raise RuntimeError(
            "charted source bytes differ from GCO_DIAGRAM_SOURCE_COMMIT after "
            f"removing only generated markers: {mismatches}. Commit substantive "
            "source changes first, then regenerate from that commit."
        )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate GCO code flowcharts (HTML + PNG).",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        metavar="PATH:FUNC",
        help=(
            "Only generate the named target(s). Repeatable. "
            "Format: ``path/to/file.py:function_name``. "
            "Default: all targets."
        ),
    )
    parser.add_argument(
        "--skip-png",
        action="store_true",
        help=(
            "Skip Playwright PNG rendering, remove selected targets' stale "
            "PNGs, and still write HTML."
        ),
    )
    parser.add_argument(
        "--require-png",
        action="store_true",
        help="Fail a canonical run if any selected PNG could not be rendered.",
    )
    parser.add_argument(
        "--skip-marker",
        action="store_true",
        help="Don't insert ``# Flowchart:`` markers into source files.",
    )
    parser.add_argument(
        "--strip-markers",
        action="store_true",
        help=(
            "Remove every existing ``# <pyflowchart-code-diagram>`` "
            "block from the source tree and exit. Useful when "
            "refactoring the generator's placement rules or when "
            "tearing down the feature entirely. Does not regenerate "
            "flowcharts — combine with a normal run afterwards if "
            "you want fresh markers."
        ),
    )
    args = parser.parse_args()
    if args.require_png and args.skip_png:
        parser.error("--require-png cannot be combined with --skip-png")

    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir = Path(__file__).resolve().parent

    if args.strip_markers:
        print("🧹 Stripping pyflowchart markers from source files")
        print("=" * 50)
        print(f"   Project root : {project_root}")
        modified = strip_all_markers(project_root)
        print("\n" + "=" * 50)
        print(f"✅ Stripped markers from {modified} file(s).")
        return

    targets = _filter_targets(TARGETS, args.target)
    full_catalog = args.target is None
    generated_at = generation_timestamp_utc()
    source_commit = generation_source_commit()
    _verify_targets_match_source_commit(
        project_root=project_root,
        targets=targets,
        source_commit=source_commit,
    )

    print("🧭 GCO Code Flowchart Generator")
    print("=" * 50)
    print(f"   Project root : {project_root}")
    print(f"   Output dir   : {output_dir}")
    print(f"   Targets      : {len(targets)}")
    print(f"   Generated at : {generated_at}")
    print(f"   Source commit: {source_commit}")

    results = render_all(
        targets=targets,
        project_root=project_root,
        output_dir=output_dir,
        render_png=not args.skip_png,
        generated_at=generated_at,
        source_commit=source_commit,
    )
    if args.require_png:
        missing_pngs = [
            result.target.source + ":" + result.target.function
            for result in results
            if result.png_path is None
        ]
        if missing_pngs:
            sys.exit(f"Canonical generation requires every PNG; missing: {missing_pngs}")

    if not args.skip_marker:
        if full_catalog:
            # Reconcile the whole owned marker set: stripping first removes
            # markers from retired targets before current targets are reinserted.
            strip_all_markers(project_root)
            upsert_markers(results, project_root=project_root)
            _sync_shared_lambda_copies(project_root)
        else:
            print(
                "\n🖋  Skipping source-marker refresh for a partial run; "
                "a full run preserves every marker entry."
            )

    if full_catalog:
        prune_orphaned_artifacts(targets=TARGETS, output_dir=output_dir)
        write_readme(results, output_dir=output_dir)
    else:
        print("\n📝 Keeping the full-catalog README unchanged for a partial run.")

    print("\n" + "=" * 50)
    print("✅ Code flowchart generation complete!")
    print(f"   Output directory: {output_dir.absolute()}")


def _sync_shared_lambda_copies(project_root: Path) -> None:
    """Propagate refreshed canonical shared Lambda sources to their copies.

    ``upsert_markers`` rewrites the pyflowchart header inside canonical
    shared sources (``lambda/tls-shared/backend_tls.py``,
    ``lambda/proxy-shared/proxy_utils.py``), but the checked-in per-function
    copies are not diagram targets, so a regeneration used to leave them one
    header behind. That drift is exactly what
    ``tests/test_lambda_shared_sources.py`` rejects and what made every
    deploy rewrite tracked files mid-run (``StackManager._sync_lambda_sources``
    re-syncs at deploy time). Reuse the deploy path's own map so the two
    sync points can never disagree about what a copy is.
    """
    synced = 0
    for source_rel, target_rels in LAMBDA_SHARED_SOURCE_TARGETS.items():
        source = project_root / source_rel
        if not source.is_file():
            continue
        source_bytes = source.read_bytes()
        for target_rel in target_rels:
            target = project_root / target_rel
            if not target.parent.is_dir():
                continue
            if target.is_file() and target.read_bytes() == source_bytes:
                continue
            target.write_bytes(source_bytes)
            synced += 1
            print(f"   Synced shared copy: {target_rel} <- {source_rel}")
    if synced:
        print(f"🔁 Refreshed {synced} shared Lambda cop{'y' if synced == 1 else 'ies'}.")


def _filter_targets(
    all_targets: list[Target],
    requested: list[str] | None,
) -> list[Target]:
    """Filter :data:`TARGETS` by optional ``PATH:FUNC`` arguments."""
    if not requested:
        return list(all_targets)
    wanted = set(requested)
    filtered = [t for t in all_targets if f"{t.source}:{t.function}" in wanted]
    missing = wanted - {f"{t.source}:{t.function}" for t in filtered}
    if missing:
        sys.exit(f"Unknown target(s): {sorted(missing)}")
    return filtered


if __name__ == "__main__":
    main()
