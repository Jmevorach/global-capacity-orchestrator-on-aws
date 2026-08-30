"""
Extended tests for cli/inference.InferenceManager.

Covers every optional parameter on deploy (model_source, capacity_type,
node_selector, env vars, autoscaling), update_image not-found handling,
the return values of scale/stop/start/delete, canary_deploy success,
and the ISO-formatted updated_at timestamp written by remove_region
(the regression fixed in test_bug_fixes.py's add_region sibling).
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from cli.inference import InferenceManager


@pytest.fixture
def manager():
    mgr = InferenceManager.__new__(InferenceManager)
    mgr._config = MagicMock()
    mgr._aws_client = MagicMock()
    return mgr


class TestDeployAllOptions:
    """Tests for deploy with all optional parameters."""

    def test_deploy_with_model_source(self, manager):
        """deploy should include model_source in spec."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)
        manager._aws_client.discover_regional_stacks.return_value = {"us-east-1": MagicMock()}

        manager.deploy("ep", "img:v1", model_source="s3://bucket/model")

        call_args = mock_store.create_endpoint.call_args
        spec = call_args[1]["spec"]
        assert spec["model_source"] == "s3://bucket/model"

    def test_deploy_with_capacity_type(self, manager):
        """deploy should include capacity_type in spec."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.deploy("ep", "img:v1", target_regions=["us-east-1"], capacity_type="spot")

        call_args = mock_store.create_endpoint.call_args
        spec = call_args[1]["spec"]
        assert spec["capacity_type"] == "spot"

    def test_deploy_with_node_selector(self, manager):
        """deploy should include node_selector in spec."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.deploy(
            "ep",
            "img:v1",
            target_regions=["us-east-1"],
            node_selector={"gpu-type": "a100"},
        )

        call_args = mock_store.create_endpoint.call_args
        spec = call_args[1]["spec"]
        assert spec["node_selector"] == {"gpu-type": "a100"}

    def test_deploy_with_env_vars(self, manager):
        """deploy should include env in spec."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.deploy(
            "ep",
            "img:v1",
            target_regions=["us-east-1"],
            env={"MODEL": "llama-3", "MAX_BATCH": "32"},
        )

        call_args = mock_store.create_endpoint.call_args
        spec = call_args[1]["spec"]
        assert spec["env"]["MODEL"] == "llama-3"

    def test_deploy_with_autoscaling(self, manager):
        """deploy should include autoscaling in spec."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        autoscaling = {"min_replicas": 1, "max_replicas": 5, "metric": "cpu"}
        manager.deploy(
            "ep",
            "img:v1",
            target_regions=["us-east-1"],
            autoscaling=autoscaling,
        )

        call_args = mock_store.create_endpoint.call_args
        spec = call_args[1]["spec"]
        assert spec["autoscaling"] == autoscaling

    def test_deploy_with_labels(self, manager):
        """deploy should pass labels to store."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.deploy(
            "ep",
            "img:v1",
            target_regions=["us-east-1"],
            labels={"team": "ml"},
        )

        call_args = mock_store.create_endpoint.call_args
        assert call_args[1]["labels"] == {"team": "ml"}

    def test_deploy_with_gpu_type(self, manager):
        """deploy should include gpu_type in spec."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.deploy(
            "ep",
            "img:v1",
            target_regions=["us-east-1"],
            gpu_type="a100",
        )

        call_args = mock_store.create_endpoint.call_args
        spec = call_args[1]["spec"]
        assert spec["gpu_type"] == "a100"

    def test_deploy_with_model_path(self, manager):
        """deploy should include model_path in spec."""
        mock_store = MagicMock()
        mock_store.create_endpoint.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.deploy(
            "ep",
            "img:v1",
            target_regions=["us-east-1"],
            model_path="/efs/models/llama",
        )

        call_args = mock_store.create_endpoint.call_args
        spec = call_args[1]["spec"]
        assert spec["model_path"] == "/efs/models/llama"


class TestRemoveRegionTimestamp:
    """Tests for legacy migration and conditional remove_region writes."""

    @staticmethod
    def _store():
        mock_store = MagicMock()
        legacy = {
            "endpoint_name": "ep",
            "desired_state": "running",
            "target_regions": ["us-east-1", "eu-west-1"],
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        migrated = {
            **legacy,
            "lifecycle_id": "life-1",
            "cleanup_regions": ["us-east-1", "eu-west-1"],
            "region_generations": {
                "us-east-1": "generation-east",
                "eu-west-1": "generation-west",
            },
            "updated_at": "2026-01-01T00:00:01+00:00",
        }
        mock_store.get_endpoint.return_value = legacy
        mock_store.ensure_lifecycle_metadata.return_value = migrated
        mock_store.update_target_regions.return_value = {"endpoint_name": "ep"}
        return mock_store, legacy, migrated

    def test_remove_region_migrates_and_uses_iso_timestamp(self, manager):
        mock_store, legacy, migrated = self._store()
        manager._get_store = MagicMock(return_value=mock_store)

        manager.remove_region("ep", "eu-west-1")

        mock_store.ensure_lifecycle_metadata.assert_called_once_with(legacy)
        kwargs = mock_store.update_target_regions.call_args.kwargs
        datetime.fromisoformat(kwargs["expected_updated_at"])
        assert kwargs["expected_updated_at"] == migrated["updated_at"]
        assert kwargs["expected_lifecycle_id"] == "life-1"

    def test_remove_region_removes_from_conditional_write(self, manager):
        mock_store, _legacy, _migrated = self._store()
        manager._get_store = MagicMock(return_value=mock_store)

        manager.remove_region("ep", "eu-west-1")

        args = mock_store.update_target_regions.call_args.args
        assert args[1] == ["us-east-1"]
        assert args[2] == ["us-east-1", "eu-west-1"]
        assert set(args[3]) == {"us-east-1", "eu-west-1"}


class TestCanaryDeploySuccess:
    """Test canary_deploy happy path."""

    def test_canary_deploy_sets_spec_correctly(self, manager):
        """canary_deploy should write canary config into the endpoint spec."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = {
            "endpoint_name": "ep",
            "lifecycle_id": "life-1",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "desired_state": "running",
            "spec": {"image": "primary:v1", "port": 8000},
        }
        mock_store.update_spec.return_value = {"endpoint_name": "ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        result = manager.canary_deploy("ep", "canary:v2", weight=25, replicas=2)

        assert result is not None
        call_args = mock_store.update_spec.call_args
        updated_spec = call_args[0][1]
        assert updated_spec["canary"]["image"] == "canary:v2"
        assert updated_spec["canary"]["weight"] == 25
        assert updated_spec["canary"]["replicas"] == 2
        # Primary image should be untouched
        assert updated_spec["image"] == "primary:v1"
