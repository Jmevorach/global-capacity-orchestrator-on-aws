"""
Regression tests for a handful of bug fixes across the GCO codebase.

Pins behavior that previously regressed: add_region now writes an ISO
timestamp to updated_at (not the region name), promote_canary and
rollback_canary validate that a canary exists and has an image field,
canary_deploy rejects weights outside 1..99 and stopped endpoints, and
both the cross-region aggregator Lambda and the shared proxy_utils
URL-encode query parameters instead of concatenating them raw. Uses
sys.path and importlib to reach the lambda/ modules that aren't on the
normal import path.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# inference.py: add_region updated_at bug fix
# ============================================================================


class TestAddRegionTimestamp:
    """Verify add_region migrates legacy identity and writes conditionally."""

    @pytest.fixture
    def manager(self):
        from cli.inference import InferenceManager

        mgr = InferenceManager.__new__(InferenceManager)
        mgr._config = MagicMock()
        mgr._aws_client = MagicMock()
        return mgr

    @staticmethod
    def _legacy_and_migrated(*, include_region: bool = False):
        regions = ["us-east-1", *(["eu-west-1"] if include_region else [])]
        legacy = {
            "endpoint_name": "my-ep",
            "desired_state": "running",
            "target_regions": regions,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        migrated = {
            **legacy,
            "lifecycle_id": "life-1",
            "cleanup_regions": list(regions),
            "region_generations": {region: f"generation-{region}" for region in regions},
            "updated_at": "2026-01-01T00:00:01+00:00",
        }
        return legacy, migrated

    def test_add_region_migrates_legacy_identity_and_uses_timestamp(self, manager):
        mock_store = MagicMock()
        legacy, migrated = self._legacy_and_migrated()
        mock_store.get_endpoint.return_value = legacy
        mock_store.ensure_lifecycle_metadata.return_value = migrated
        mock_store.update_target_regions.return_value = {"endpoint_name": "my-ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.add_region("my-ep", "eu-west-1")

        mock_store.ensure_lifecycle_metadata.assert_called_once_with(legacy)
        kwargs = mock_store.update_target_regions.call_args.kwargs
        datetime.fromisoformat(kwargs["expected_updated_at"])
        assert kwargs["expected_updated_at"] == migrated["updated_at"]
        assert kwargs["expected_lifecycle_id"] == "life-1"

    def test_add_region_includes_new_region_in_conditional_write(self, manager):
        mock_store = MagicMock()
        legacy, migrated = self._legacy_and_migrated()
        mock_store.get_endpoint.return_value = legacy
        mock_store.ensure_lifecycle_metadata.return_value = migrated
        mock_store.update_target_regions.return_value = {"endpoint_name": "my-ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        manager.add_region("my-ep", "eu-west-1")

        args = mock_store.update_target_regions.call_args.args
        assert args[1] == ["us-east-1", "eu-west-1"]
        assert args[2] == ["us-east-1", "eu-west-1"]
        assert set(args[3]) == {"us-east-1", "eu-west-1"}

    def test_add_region_does_not_duplicate(self, manager):
        mock_store = MagicMock()
        legacy, migrated = self._legacy_and_migrated(include_region=True)
        mock_store.get_endpoint.return_value = legacy
        mock_store.ensure_lifecycle_metadata.return_value = migrated
        manager._get_store = MagicMock(return_value=mock_store)

        result = manager.add_region("my-ep", "eu-west-1")

        assert result == migrated
        mock_store.update_target_regions.assert_not_called()


# ============================================================================
# inference.py: promote_canary defensive validation
# ============================================================================


class TestPromoteCanaryValidation:
    """Verify promote_canary validates canary structure."""

    @pytest.fixture
    def manager(self):
        from cli.inference import InferenceManager

        mgr = InferenceManager.__new__(InferenceManager)
        mgr._config = MagicMock()
        mgr._aws_client = MagicMock()
        return mgr

    def test_promote_canary_missing_image_raises(self, manager):
        """promote_canary should raise if canary dict has no 'image' key."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = {
            "endpoint_name": "my-ep",
            "lifecycle_id": "life-1",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "spec": {"image": "old:v1", "canary": {"weight": 10, "replicas": 1}},
        }
        manager._get_store = MagicMock(return_value=mock_store)

        with pytest.raises(ValueError, match="missing the 'image' field"):
            manager.promote_canary("my-ep")

    def test_promote_canary_no_canary_raises(self, manager):
        """promote_canary should raise if no canary deployment exists."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = {
            "endpoint_name": "my-ep",
            "lifecycle_id": "life-1",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "spec": {"image": "old:v1"},
        }
        manager._get_store = MagicMock(return_value=mock_store)

        with pytest.raises(ValueError, match="no active canary"):
            manager.promote_canary("my-ep")

    def test_promote_canary_success(self, manager):
        """promote_canary should swap image and remove canary config."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = {
            "endpoint_name": "my-ep",
            "lifecycle_id": "life-1",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "spec": {
                "image": "old:v1",
                "canary": {"image": "new:v2", "weight": 20, "replicas": 1},
            },
        }
        mock_store.update_spec.return_value = {"endpoint_name": "my-ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        result = manager.promote_canary("my-ep")
        assert result is not None

        # Verify the spec passed to update_spec
        call_args = mock_store.update_spec.call_args
        updated_spec = call_args[0][1]
        assert updated_spec["image"] == "new:v2"
        assert "canary" not in updated_spec

    def test_promote_canary_not_found(self, manager):
        """promote_canary should return None if endpoint not found."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = None
        manager._get_store = MagicMock(return_value=mock_store)

        result = manager.promote_canary("ghost")
        assert result is None


# ============================================================================
# inference.py: rollback_canary edge cases
# ============================================================================


class TestRollbackCanary:
    """Tests for rollback_canary."""

    @pytest.fixture
    def manager(self):
        from cli.inference import InferenceManager

        mgr = InferenceManager.__new__(InferenceManager)
        mgr._config = MagicMock()
        mgr._aws_client = MagicMock()
        return mgr

    def test_rollback_removes_canary_keeps_primary(self, manager):
        """rollback should remove canary config but keep primary image."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = {
            "endpoint_name": "my-ep",
            "lifecycle_id": "life-1",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "spec": {
                "image": "primary:v1",
                "canary": {"image": "canary:v2", "weight": 10},
            },
        }
        mock_store.update_spec.return_value = {"endpoint_name": "my-ep"}
        manager._get_store = MagicMock(return_value=mock_store)

        result = manager.rollback_canary("my-ep")
        assert result is not None

        call_args = mock_store.update_spec.call_args
        updated_spec = call_args[0][1]
        assert updated_spec["image"] == "primary:v1"
        assert "canary" not in updated_spec

    def test_rollback_no_canary_raises(self, manager):
        """rollback should raise if no canary exists."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = {
            "endpoint_name": "my-ep",
            "lifecycle_id": "life-1",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "spec": {"image": "primary:v1"},
        }
        manager._get_store = MagicMock(return_value=mock_store)

        with pytest.raises(ValueError, match="no active canary"):
            manager.rollback_canary("my-ep")


# ============================================================================
# inference.py: canary_deploy validation
# ============================================================================


class TestCanaryDeployValidation:
    """Tests for canary_deploy input validation."""

    @pytest.fixture
    def manager(self):
        from cli.inference import InferenceManager

        mgr = InferenceManager.__new__(InferenceManager)
        mgr._config = MagicMock()
        mgr._aws_client = MagicMock()
        return mgr

    def test_canary_weight_zero_raises(self, manager):
        """Weight of 0 should raise ValueError."""
        with pytest.raises(ValueError, match="between 1 and 99"):
            manager.canary_deploy("ep", "img:v2", weight=0)

    def test_canary_weight_100_raises(self, manager):
        """Weight of 100 should raise ValueError."""
        with pytest.raises(ValueError, match="between 1 and 99"):
            manager.canary_deploy("ep", "img:v2", weight=100)

    def test_canary_on_stopped_endpoint_raises(self, manager):
        """Canary on a stopped endpoint should raise."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = {
            "endpoint_name": "ep",
            "lifecycle_id": "life-1",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "desired_state": "stopped",
            "spec": {"image": "old:v1"},
        }
        manager._get_store = MagicMock(return_value=mock_store)

        with pytest.raises(ValueError, match="must be running"):
            manager.canary_deploy("ep", "new:v2", weight=10)

    def test_canary_not_found_returns_none(self, manager):
        """Canary on non-existent endpoint should return None."""
        mock_store = MagicMock()
        mock_store.get_endpoint.return_value = None
        manager._get_store = MagicMock(return_value=mock_store)

        result = manager.canary_deploy("ghost", "img:v2")
        assert result is None


# ============================================================================
# cross-region-aggregator: URL encoding
# ============================================================================


class TestQueryRegionUrlEncoding:
    """Verify query params are properly URL-encoded."""

    def test_special_chars_in_query_params(self):
        """Query params with special characters should be URL-encoded."""
        from tests._lambda_imports import load_lambda_module

        handler = load_lambda_module("cross-region-aggregator")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps({"ok": True}).encode("utf-8")
        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with (
            patch.dict(handler.os.environ, {"AWS_URL_SUFFIX": "amazonaws.com"}),
            patch.object(handler, "http", mock_http),
            patch.object(handler, "_sigv4_headers", return_value={"Authorization": "test"}),
        ):
            handler.query_region(
                "us-east-1",
                "https://abc123.execute-api.us-east-1.amazonaws.com/prod",
                "/api/v1/jobs",
                "GET",
                query_params={"namespace": "my namespace", "label": "app=web&tier=front"},
            )

            call_args = mock_http.request.call_args
            url = call_args[0][1]
            # Should be URL-encoded, not raw
            assert "my+namespace" in url or "my%20namespace" in url
            assert "app%3Dweb%26tier%3Dfront" in url or "app%3Dweb%26" in url
            # Should NOT contain raw special chars in query string
            assert "my namespace" not in url.split("?")[1]


# ============================================================================
# proxy_utils.py: URL encoding
# ============================================================================


class TestBuildTargetUrlEncoding:
    """Verify build_target_url properly URL-encodes query params."""

    def test_special_chars_encoded(self):
        """Query params with special characters should be URL-encoded."""
        from tests._lambda_imports import load_lambda_module

        proxy_utils = load_lambda_module("proxy-shared", "proxy_utils", shared_dirs=["tls-shared"])

        url = proxy_utils.build_target_url(
            "alb.example.com",
            "/api/v1/jobs",
            {"namespace": "my namespace", "filter": "a=b&c=d"},
        )

        assert "my+namespace" in url or "my%20namespace" in url
        assert "a%3Db%26c%3Dd" in url or "a%3Db%26" in url

    def test_no_query_params(self):
        """URL without query params should have no question mark."""
        from tests._lambda_imports import load_lambda_module

        proxy_utils = load_lambda_module("proxy-shared", "proxy_utils", shared_dirs=["tls-shared"])

        url = proxy_utils.build_target_url("alb.example.com", "/api/v1/health", None)

        assert url == "https://alb.example.com/api/v1/health"
        assert "?" not in url

    def test_empty_query_params(self):
        """Empty query params dict should produce no query string."""
        from tests._lambda_imports import load_lambda_module

        proxy_utils = load_lambda_module("proxy-shared", "proxy_utils", shared_dirs=["tls-shared"])

        url = proxy_utils.build_target_url("alb.example.com", "/api/v1/health", {})

        # Empty dict is falsy, so no query string
        assert "?" not in url
