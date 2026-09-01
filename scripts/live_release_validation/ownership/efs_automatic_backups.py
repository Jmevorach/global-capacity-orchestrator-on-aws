"""Accepted residue for AWS-managed EFS automatic backup recovery points.

Amazon EFS automatic backups are stored in the AWS-managed
``aws/efs/automatic-backup-vault``.  That vault denies manual recovery-point
deletion and expires each point on its calculated lifecycle.  A validation run
that deletes its EFS file system can therefore leave one non-billable-by-stack,
non-deletable recovery point for the retention window.

This module removes only that exact shape from inventory after independently
proving vault identity and policy, EFS resource identity and absence, project
ownership, and scheduled deletion.  It performs no AWS mutations.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from botocore.exceptions import ClientError

from ..constants import _RUN_STACK_TAG
from ..inventory._shared import _mapping_tags, _name_or_path_is_project_owned
from ..json_utils import loads_without_duplicate_keys
from ..models import RunContext

_EFS_AUTOMATIC_BACKUP_VAULT = "aws/efs/automatic-backup-vault"
_DELETE_RECOVERY_POINT_ACTION = "backup:DeleteRecoveryPoint"
_RECOVERY_POINT_RESOURCE = re.compile(r"^recovery-point:[A-Za-z0-9-]+$")
_EFS_FILE_SYSTEM_RESOURCE = re.compile(r"^file-system/(?P<id>fs-[0-9a-f]{8,40})$")
_VALIDATION_RUN_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+=@-]{0,255}$")


def _string_values(value: object) -> list[str] | None:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return None


def _all_principals(value: object) -> bool:
    if value == "*":
        return True
    if not isinstance(value, Mapping) or set(value) != {"AWS"}:
        return False
    principals = _string_values(value["AWS"])
    return principals is not None and principals == ["*"]


def _policy_has_unconditional_delete_deny(policy_text: str, recovery_point_arn: str) -> bool:
    try:
        policy = loads_without_duplicate_keys(policy_text)
    except ValueError as exc:
        raise RuntimeError("EFS automatic backup vault policy is invalid JSON") from exc
    if not isinstance(policy, dict):
        raise RuntimeError("EFS automatic backup vault policy must be an object")
    raw_statements = policy.get("Statement")
    statements = raw_statements if isinstance(raw_statements, list) else [raw_statements]
    for statement in statements:
        if not isinstance(statement, dict) or statement.get("Effect") != "Deny":
            continue
        if any(
            key in statement for key in ("Condition", "NotAction", "NotPrincipal", "NotResource")
        ):
            continue
        actions = _string_values(statement.get("Action"))
        resources = _string_values(statement.get("Resource"))
        if (
            actions is not None
            and _DELETE_RECOVERY_POINT_ACTION in actions
            and resources is not None
            and ("*" in resources or recovery_point_arn in resources)
            and _all_principals(statement.get("Principal"))
        ):
            return True
    return False


def _arn_parts(arn: str) -> tuple[str, str, str, str, str] | None:
    parts = arn.split(":", 5)
    if len(parts) != 6 or parts[0] != "arn":
        return None
    return parts[1], parts[2], parts[3], parts[4], parts[5]


def _accepted_recovery_point(
    ctx: RunContext,
    *,
    region: str,
    recovery_point_arn: str,
) -> dict[str, Any] | None:
    partition = ctx.session.get_partition_for_region(region)
    if not isinstance(partition, str) or not partition:
        raise RuntimeError(f"Could not resolve AWS partition for automatic EFS backup in {region}")
    expected_account = ctx.settings.expected_account
    parsed = _arn_parts(recovery_point_arn)
    if parsed is None:
        return None
    arn_partition, service, arn_region, account, resource = parsed
    if (
        arn_partition != partition
        or service != "backup"
        or arn_region != region
        or account != expected_account
        or _RECOVERY_POINT_RESOURCE.fullmatch(resource) is None
    ):
        return None

    backup = ctx.session.client("backup", region_name=region)
    description = backup.describe_recovery_point(
        BackupVaultName=_EFS_AUTOMATIC_BACKUP_VAULT,
        RecoveryPointArn=recovery_point_arn,
    )
    expected_vault_arn = (
        f"arn:{partition}:backup:{region}:{expected_account}:"
        f"backup-vault:{_EFS_AUTOMATIC_BACKUP_VAULT}"
    )
    if (
        description.get("RecoveryPointArn") != recovery_point_arn
        or description.get("BackupVaultName") != _EFS_AUTOMATIC_BACKUP_VAULT
        or description.get("BackupVaultArn") != expected_vault_arn
    ):
        return None
    source_vault_arn = str(description.get("SourceBackupVaultArn") or "")
    if source_vault_arn and source_vault_arn != expected_vault_arn:
        return None
    if description.get("ResourceType") != "EFS" or description.get("Status") != "COMPLETED":
        return None

    resource_arn = str(description.get("ResourceArn") or "")
    resource_parts = _arn_parts(resource_arn)
    if resource_parts is None:
        return None
    resource_partition, resource_service, resource_region, resource_account, resource = (
        resource_parts
    )
    file_system_match = _EFS_FILE_SYSTEM_RESOURCE.fullmatch(resource)
    if (
        resource_partition != partition
        or resource_service != "elasticfilesystem"
        or resource_region != region
        or resource_account != expected_account
        or file_system_match is None
    ):
        return None
    resource_name = str(description.get("ResourceName") or "")
    if not _name_or_path_is_project_owned(resource_name, ctx.config.project_name):
        return None

    lifecycle = description.get("CalculatedLifecycle")
    delete_at = lifecycle.get("DeleteAt") if isinstance(lifecycle, Mapping) else None
    if (
        not isinstance(delete_at, datetime)
        or delete_at.tzinfo is None
        or delete_at.utcoffset() is None
    ):
        return None

    tags = _mapping_tags(backup.list_tags(ResourceArn=recovery_point_arn).get("Tags"))
    validation_run = str(tags.get(_RUN_STACK_TAG) or "")
    if validation_run and _VALIDATION_RUN_TAG.fullmatch(validation_run) is None:
        return None

    vault = backup.describe_backup_vault(BackupVaultName=_EFS_AUTOMATIC_BACKUP_VAULT)
    if (
        vault.get("BackupVaultName") != _EFS_AUTOMATIC_BACKUP_VAULT
        or vault.get("BackupVaultArn") != expected_vault_arn
    ):
        return None
    policy_text = backup.get_backup_vault_access_policy(
        BackupVaultName=_EFS_AUTOMATIC_BACKUP_VAULT
    ).get("Policy")
    if not isinstance(policy_text, str) or not _policy_has_unconditional_delete_deny(
        policy_text, recovery_point_arn
    ):
        return None

    file_system_id = file_system_match.group("id")
    efs = ctx.session.client("efs", region_name=region)
    try:
        efs.describe_file_systems(FileSystemId=file_system_id)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "FileSystemNotFound":
            raise
    else:
        return None

    return {
        "region": region,
        "account": expected_account,
        "partition": partition,
        "recovery_point_arn": recovery_point_arn,
        "backup_vault_name": _EFS_AUTOMATIC_BACKUP_VAULT,
        "backup_vault_arn": expected_vault_arn,
        "resource_type": "EFS",
        "resource_name": resource_name,
        "resource_arn": resource_arn,
        "file_system_id": file_system_id,
        "source_file_system_absent": True,
        "source_absence_authority": "efs:DescribeFileSystems FileSystemNotFound",
        "delete_at": delete_at.isoformat(),
        "tags": tags,
        "validation_run_tag": validation_run or None,
        "vault_policy_unconditional_delete_deny": True,
        "note": (
            "AWS-managed EFS automatic backups deny manual deletion and expire "
            "at their calculated lifecycle date"
        ),
    }


def _strip_accepted_efs_automatic_backup_recovery_points(
    ctx: RunContext,
    project_inventory: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Strip only proven, expiring AWS-managed backups of absent EFS sources."""
    inventory = copy.deepcopy(project_inventory)
    accepted: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    regional = inventory.get("regional")
    if not isinstance(regional, dict):
        return inventory, accepted

    for raw_region, resources in list(regional.items()):
        region = str(raw_region)
        if not isinstance(resources, dict):
            raise RuntimeError(f"Project inventory for {region} must be an object")
        candidates = resources.get("backup_recovery_points", [])
        if not isinstance(candidates, list):
            raise RuntimeError(f"Backup recovery-point inventory for {region} must be a list")
        kept: list[str] = []
        accepted_arns: set[str] = set()
        for candidate in candidates:
            arn = str(candidate or "")
            identity = (region, arn)
            if not arn or identity in seen:
                raise RuntimeError(f"Duplicate or empty backup recovery-point identity in {region}")
            seen.add(identity)
            evidence = _accepted_recovery_point(
                ctx,
                region=region,
                recovery_point_arn=arn,
            )
            if evidence is None:
                kept.append(arn)
                continue
            accepted_arns.add(arn)
            accepted.append(evidence)
        resources["backup_recovery_points"] = kept

        tagged = resources.get("tagged_resources")
        if tagged is not None:
            if not isinstance(tagged, list):
                raise RuntimeError(f"Tagged-resource inventory for {region} must be a list")
            resources["tagged_resources"] = [
                entry
                for entry in tagged
                if not (isinstance(entry, dict) and str(entry.get("arn") or "") in accepted_arns)
            ]
        if not any(resources.values()):
            regional.pop(raw_region)
    return inventory, accepted
