"""Unit tests for intune2snipe (no live Graph/Snipe calls)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from app import (
    GraphClient,
    SnipeITClient,
    SyncConfig,
    SyncOutcome,
    UserSyncOutcome,
    _assigned_user_id,
    _autopilot_pending,
    _build_asset_payload,
    _build_entra_user_payload,
    _device_in_retire_state,
    _device_user_upn,
    _enrich_device_autopilot,
    _env_status_name,
    _format_summary,
    _managed_devices_url,
    _parse_group_ids,
    _parse_graph_datetime,
    _platform_includes_windows,
    _status_unavailable,
    _upn_location_prefix,
    fetch_entra_group_users,
    fetch_group_device_ids,
    fetch_managed_devices,
    normalize_upn,
    reconcile_missing_devices,
    sync_device,
    sync_entra_user,
    sync_entra_users,
)


def _test_config(**kwargs: object) -> SyncConfig:
    defaults = {
        "checkout_mode": "user",
        "location_prefix_len": 3,
        "use_primary_user": False,
        "checkout_on_create": True,
    }
    defaults.update(kwargs)
    return SyncConfig(**defaults)  # type: ignore[arg-type]


class TestNormalizeUpn:
    def test_none(self) -> None:
        assert normalize_upn(None) is None

    def test_strips_android_guid_prefix(self) -> None:
        raw = "a" * 32 + "user@domain.com"
        assert normalize_upn(raw) == "user@domain.com"

    def test_plain_upn(self) -> None:
        assert normalize_upn("user@domain.com") == "user@domain.com"


class TestParseGroupIds:
    def test_empty(self) -> None:
        assert _parse_group_ids(None) == []
        assert _parse_group_ids("") == []

    def test_splits_and_trims(self) -> None:
        assert _parse_group_ids(" a , b , ") == ["a", "b"]


class TestFetchGroupDeviceIds:
    def test_no_groups_returns_none(self) -> None:
        g = MagicMock()
        assert fetch_group_device_ids(g, []) is None
        g.get_paginated.assert_not_called()

    def test_collects_device_ids(self) -> None:
        g = MagicMock()
        g.get_paginated.return_value = [{"id": "d1"}, {"id": "d2"}]
        out = fetch_group_device_ids(g, ["g1"])
        assert out == {"d1", "d2"}
        g.get_paginated.assert_called_once()
        assert "groups/g1" in g.get_paginated.call_args[0][0]
        assert "microsoft.graph.device" in g.get_paginated.call_args[0][0]

    def test_403_raises_runtime_error(self) -> None:
        g = MagicMock()

        def boom(_url: str) -> list[dict]:
            resp = requests.Response()
            resp.status_code = 403
            raise requests.HTTPError(response=resp)

        g.get_paginated.side_effect = boom
        with pytest.raises(RuntimeError, match="403 Forbidden"):
            fetch_group_device_ids(g, ["g1"])


class TestManagedDevicesUrl:
    def test_select_and_filter_windows(self) -> None:
        url = _managed_devices_url("windows")
        assert "%24select=" in url or "$select=" in url
        assert "serialNumber" in url
        assert "%24filter=" in url or "$filter=" in url
        assert "Windows" in url

    def test_all_platform_no_filter(self) -> None:
        url = _managed_devices_url("all")
        assert "%24select=" in url or "$select=" in url
        assert "%24filter=" not in url and "$filter=" not in url


class TestDeviceUserUpn:
    def test_primary_user_when_enabled(self) -> None:
        config = _test_config(use_primary_user=True)
        device = {"id": "d1", "userPrincipalName": "enrolled@domain.com"}
        assert _device_user_upn(device, {"d1": "primary@domain.com"}, config) == "primary@domain.com"

    def test_email_fallback(self) -> None:
        config = _test_config()
        device = {"emailAddress": "mail@domain.com"}
        assert _device_user_upn(device, {}, config) == "mail@domain.com"


class TestFindAssetBySerial:
    def test_uses_path_not_query_param(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config())
            c._session = MagicMock()
            c._session.get.return_value.json.return_value = {
                "rows": [{"id": 99, "serial": "SN123"}]
            }
            c._session.get.return_value.raise_for_status = MagicMock()
            assert c.find_asset_by_serial("SN123") == {"id": 99, "serial": "SN123"}
            url = c._session.get.call_args[0][0]
            assert url.endswith("/api/v1/hardware/byserial/SN123")

    def test_returns_none_when_snipe_reports_not_found(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config())
            c._session = MagicMock()
            c._session.get.return_value.json.return_value = {
                "status": "error",
                "messages": "Asset does not exist.",
            }
            c._session.get.return_value.raise_for_status = MagicMock()
            assert c.find_asset_by_serial("NEW-SERIAL") is None


class TestSnipeTaxonomyLookup:
    def test_manufacturer_case_insensitive_match(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config())
            c._session = MagicMock()
            c._session.get.return_value.json.return_value = {
                "rows": [{"id": 5, "name": "Lenovo"}]
            }
            c._session.get.return_value.raise_for_status = MagicMock()
            assert c.get_or_create_manufacturer("LENOVO") == 5
            c._session.post.assert_not_called()

    def test_dry_run_skips_taxonomy_writes(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config())
            c._session = MagicMock()
            c._session.get.return_value.json.return_value = {"rows": []}
            c._session.get.return_value.raise_for_status = MagicMock()
            assert c.get_or_create_manufacturer("Dell", dry_run=True) is None
            assert c.get_or_create_model("XPS", 1, 2, dry_run=True) is None
            c._session.post.assert_not_called()


class TestSnipeGetUserId:
    def test_email_exact_match(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config())
            c._session = MagicMock()
            c._session.get.return_value.json.return_value = {
                "rows": [{"id": 42, "email": "user@domain.com", "username": "user"}]
            }
            c._session.get.return_value.raise_for_status = MagicMock()
            assert c.get_user_id("user@domain.com") == 42
            params = c._session.get.call_args_list[0][1]["params"]
            assert params.get("email") == "user@domain.com"

    def test_username_case_insensitive(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config())
            c._session = MagicMock()
            c._session.get.return_value.json.return_value = {
                "rows": [{"id": 7, "username": "JDOE", "email": ""}]
            }
            c._session.get.return_value.raise_for_status = MagicMock()
            assert c.get_user_id("jdoe") == 7


class TestBuildAssetPayload:
    def test_create_includes_checkout_on_create(self) -> None:
        config = _test_config(checkout_on_create=True)
        payload = _build_asset_payload(
            {"osVersion": "11", "managedDeviceOwnerType": "personal"},
            device_name="pc",
            serial="SN1",
            man_id=1,
            mod_id=2,
            status_id=3,
            config=config,
            man_name="Dell",
            mod_number="XPS",
            checkout_mode="user",
            checkout_target_id=9,
            for_create=True,
        )
        assert payload["assigned_user"] == 9
        assert payload["byod"] == 1
        assert payload["asset_tag"] == "pc"
        assert "OS 11" in payload["notes"]

    def test_create_asset_tag_falls_back_to_serial(self) -> None:
        config = _test_config()
        payload = _build_asset_payload(
            {},
            device_name="",
            serial="SN-FALLBACK",
            man_id=1,
            mod_id=2,
            status_id=3,
            config=config,
            man_name="Dell",
            mod_number="XPS",
            checkout_mode="user",
            checkout_target_id=None,
            for_create=True,
        )
        assert payload["asset_tag"] == "SN-FALLBACK"

    def test_update_omits_asset_tag(self) -> None:
        config = _test_config()
        payload = _build_asset_payload(
            {"osVersion": "11"},
            device_name="pc",
            serial="SN1",
            man_id=1,
            mod_id=2,
            status_id=99,
            config=config,
            man_name="Dell",
            mod_number="XPS",
            checkout_mode="user",
            checkout_target_id=None,
            for_create=False,
        )
        assert "asset_tag" not in payload

    def test_update_includes_status_id(self) -> None:
        config = _test_config()
        payload = _build_asset_payload(
            {"osVersion": "11"},
            device_name="pc",
            serial="SN1",
            man_id=1,
            mod_id=2,
            status_id=99,
            config=config,
            man_name="Dell",
            mod_number="XPS",
            checkout_mode="user",
            checkout_target_id=None,
            for_create=False,
        )
        assert payload["status_id"] == 99
        assert payload["manufacturer_id"] == 1


class TestSnipeLocationCheckout:
    def test_upn_location_prefix(self) -> None:
        assert _upn_location_prefix("A55@domain.com", 3) == "A55"
        assert _upn_location_prefix("user@domain.com", 3) == "use"
        assert _upn_location_prefix(None, 3) is None

    def test_get_location_id_matches_name_prefix(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config())
            c._session = MagicMock()
            c._session.get.return_value.json.return_value = {
                "rows": [{"id": 9, "name": "A55 - somewhere"}]
            }
            c._session.get.return_value.raise_for_status = MagicMock()
            assert c.get_location_id("A55@domain.com", prefix_len=3) == 9

    def test_create_checks_out_to_location_on_create(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = None
        snipe.get_or_create_manufacturer.return_value = 1
        snipe.get_or_create_model.return_value = 2
        snipe.get_location_id.return_value = 9
        snipe.create_asset.return_value = {"id": 11}
        config = _test_config(checkout_mode="location", checkout_on_create=True)
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "manufacturer": "Dell",
            "model": "XPS",
            "userPrincipalName": "A55@domain.com",
        }
        assert (
            sync_device(
                snipe,
                dev,
                category_id=1,
                default_status_id=2,
                config=config,
                dry_run=False,
            )
            == SyncOutcome.CREATED
        )
        snipe.get_location_id.assert_called_once_with("A55@domain.com", 3)
        create_payload = snipe.create_asset.call_args[0][0]
        assert create_payload["assigned_location"] == 9
        snipe.checkout_asset_to_location.assert_not_called()


class TestSyncDeviceOutcomes:
    def test_skipped_no_serial(self) -> None:
        snipe = MagicMock()
        dev = {"deviceName": "n", "serialNumber": None}
        assert (
            sync_device(
                snipe, dev, category_id=1, default_status_id=2, config=_test_config()
            )
            == SyncOutcome.SKIPPED_NO_SERIAL
        )
        snipe.ensure_asset_for_sync.assert_not_called()

    def test_dry_run_create(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = None
        snipe.get_or_create_manufacturer.return_value = 1
        snipe.get_or_create_model.return_value = 2
        snipe.get_user_id.return_value = None
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "manufacturer": "Dell",
            "model": "XPS",
        }
        assert (
            sync_device(
                snipe,
                dev,
                category_id=1,
                default_status_id=2,
                config=_test_config(),
                dry_run=True,
            )
            == SyncOutcome.DRY_RUN_CREATE
        )

    def test_update_rechecks_out_when_user_changes(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = {
            "id": 10,
            "assigned_to": {"id": 1, "name": "old@domain.com"},
        }
        snipe.get_or_create_manufacturer.return_value = 1
        snipe.get_or_create_model.return_value = 2
        snipe.get_user_id.return_value = 2
        snipe.update_asset.return_value = True
        snipe.checkout_asset.return_value = True
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "manufacturer": "Dell",
            "model": "XPS",
            "userPrincipalName": "new@domain.com",
        }
        assert (
            sync_device(
                snipe,
                dev,
                category_id=1,
                default_status_id=2,
                config=_test_config(checkout_on_create=False),
                dry_run=False,
            )
            == SyncOutcome.UPDATED
        )
        snipe.checkout_asset.assert_called_once_with(10, 2)

    def test_update_skips_checkout_when_user_unchanged(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = {
            "id": 10,
            "assigned_to": {"id": 2, "name": "user@domain.com"},
        }
        snipe.get_or_create_manufacturer.return_value = 1
        snipe.get_or_create_model.return_value = 2
        snipe.get_user_id.return_value = 2
        snipe.update_asset.return_value = True
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "manufacturer": "Dell",
            "model": "XPS",
            "userPrincipalName": "user@domain.com",
        }
        assert (
            sync_device(
                snipe,
                dev,
                category_id=1,
                default_status_id=2,
                config=_test_config(),
                dry_run=False,
            )
            == SyncOutcome.UPDATED
        )
        snipe.checkout_asset.assert_not_called()

    def test_update_checks_in_when_primary_user_cleared(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = {
            "id": 10,
            "assigned_to": {"id": 1, "name": "old@domain.com"},
        }
        snipe.get_or_create_manufacturer.return_value = 1
        snipe.get_or_create_model.return_value = 2
        snipe.get_user_id.return_value = None
        snipe.update_asset.return_value = True
        snipe.checkin_asset.return_value = True
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "manufacturer": "Dell",
            "model": "XPS",
            "userPrincipalName": None,
        }
        assert (
            sync_device(
                snipe,
                dev,
                category_id=1,
                default_status_id=2,
                config=_test_config(),
                dry_run=False,
            )
            == SyncOutcome.UPDATED
        )
        snipe.checkin_asset.assert_called_once_with(10)
        snipe.checkout_asset.assert_not_called()


class TestLifecycle:
    def test_retire_state_detection(self) -> None:
        assert _device_in_retire_state({"managementState": "wipePending"})
        assert not _device_in_retire_state({"managementState": "managed"})

    def test_autopilot_pending_states(self) -> None:
        assert _autopilot_pending({"enrollmentState": "pendingReset"})
        assert not _autopilot_pending({"enrollmentState": "enrolled"})

    def test_enrich_device_autopilot(self) -> None:
        dev: dict = {}
        _enrich_device_autopilot(
            dev, {"enrollmentState": "enrolled", "lastContactedDateTime": "2024-01-01"}
        )
        assert dev["_autopilot_enrollmentState"] == "enrolled"

    def test_platform_includes_windows(self) -> None:
        assert _platform_includes_windows("windows")
        assert _platform_includes_windows("all")
        assert not _platform_includes_windows("ios")

    def test_retiring_device_lifecycle(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = {
            "id": 10,
            "assigned_to": {"id": 1},
        }
        snipe.checkin_asset.return_value = True
        snipe.apply_lifecycle_update.return_value = True
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "managementState": "wipePending",
            "manufacturer": "Dell",
            "model": "XPS",
        }
        config = _test_config()
        outcome = sync_device(
            snipe,
            dev,
            category_id=1,
            default_status_id=2,
            config=config,
            status_ids={"pending_retire": 55},
            dry_run=False,
        )
        assert outcome == SyncOutcome.LIFECYCLE_PENDING_RETIRE
        snipe.checkin_asset.assert_called_once_with(10)
        snipe.apply_lifecycle_update.assert_called_once()
        assert snipe.get_or_create_model.call_count == 0

    def test_reconcile_archived_when_missing_from_intune(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = {"id": 20, "assigned_to": {"id": 3}}
        snipe.checkin_asset.return_value = True
        snipe.apply_lifecycle_update.return_value = True
        config = _test_config(
            sync_state_file="/tmp/state.json",
            lifecycle_reconciliation=True,
        )
        previous = {
            "SN9": {
                "platform": "ios",
                "device_name": "phone",
                "last_sync": "2024-01-01",
            }
        }
        counts = reconcile_missing_devices(
            snipe,
            config,
            previous,
            current_intune_serials=set(),
            autopilot_by_serial={},
            platform="all",
            default_status_id=2,
            status_ids={"archived": 88, "pending_autopilot": 77},
            dry_run=False,
        )
        assert counts[SyncOutcome.LIFECYCLE_ARCHIVED] == 1
        snipe.apply_lifecycle_update.assert_called_once()
        call_kw = snipe.apply_lifecycle_update.call_args[1]
        assert call_kw["archived"] is True
        assert call_kw["status_id"] == 88

    def test_reconcile_pending_autopilot_for_windows(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = {"id": 21}
        snipe.checkin_asset.return_value = True
        snipe.apply_lifecycle_update.return_value = True
        config = _test_config(
            sync_state_file="/tmp/state.json",
            lifecycle_reconciliation=True,
        )
        previous = {"SNW": {"platform": "windows", "device_name": "laptop"}}
        autopilot = {"snw": {"enrollmentState": "pendingReset", "serialNumber": "SNW"}}
        counts = reconcile_missing_devices(
            snipe,
            config,
            previous,
            current_intune_serials=set(),
            autopilot_by_serial=autopilot,
            platform="windows",
            default_status_id=2,
            status_ids={"archived": 88, "pending_autopilot": 77},
            dry_run=False,
        )
        assert counts[SyncOutcome.LIFECYCLE_PENDING_AUTOPILOT] == 1
        assert snipe.apply_lifecycle_update.call_args[1]["status_id"] == 77
        assert snipe.apply_lifecycle_update.call_args[1]["archived"] is False


class TestSnipeRestore:
    def test_ensure_asset_restores_deleted(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNIPEIT_URL": "https://snipe.example.com/api/v1",
                "SNIPEIT_API_TOKEN": "token",
            },
            clear=False,
        ):
            c = SnipeITClient(_test_config(restore_deleted_assets=True))
            c._session = MagicMock()
            deleted = {"id": 5, "serial": "SN1", "deleted_at": "2024-01-01"}
            active = {"id": 5, "serial": "SN1"}
            c._session.get.return_value.raise_for_status = MagicMock()
            c._session.get.return_value.json.side_effect = [
                {"rows": [deleted]},
                {"rows": [active]},
            ]
            c._session.post.return_value.json.return_value = {"status": "success"}
            c._session.post.return_value.raise_for_status = MagicMock()
            asset = c.ensure_asset_for_sync("SN1", config=_test_config())
            assert asset == active
            c._session.post.assert_called_once()
            assert "/hardware/5/restore" in c._session.post.call_args[0][0]


class TestGraphAutopilot:
    def test_fetch_autopilot_by_serial(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
            },
            clear=False,
        ):
            gc = GraphClient()
            gc._token = "tok"
            gc._token_expires_at = __import__("time").time() + 3600
            gc.get_paginated = MagicMock(
                return_value=[
                    {"serialNumber": "ABC123", "enrollmentState": "enrolled"},
                    {"serialNumber": "", "enrollmentState": "failed"},
                ]
            )
            result = gc.fetch_autopilot_by_serial()
            assert result == {"abc123": {"serialNumber": "ABC123", "enrollmentState": "enrolled"}}


class TestAssignedUserId:
    def test_reads_assigned_to_id(self) -> None:
        assert _assigned_user_id({"assigned_to": {"id": 5}}) == 5

    def test_missing_assignee(self) -> None:
        assert _assigned_user_id({}) is None
        assert _assigned_user_id(None) is None


class TestFormatSummary:
    def test_formats_counts(self) -> None:
        counts = {o: 0 for o in SyncOutcome}
        counts[SyncOutcome.CREATED] = 2
        counts[SyncOutcome.UPDATED] = 1
        s = _format_summary(counts, dry_run=False)
        assert "2 created" in s
        assert "1 updated" in s


class TestGraphTokenRefresh:
    def test_ensure_auth_skips_while_fresh(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
            },
            clear=False,
        ):
            gc = GraphClient()
            gc._token = "tok"
            gc._token_expires_at = __import__("time").time() + 3600
            gc._ensure_auth()
            assert gc._token == "tok"


class TestGraphPrimaryUserBatch:
    def test_batch_maps_device_to_upn(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
            },
            clear=False,
        ):
            gc = GraphClient()
            gc._token = "tok"
            gc._token_expires_at = __import__("time").time() + 3600
            gc._session = MagicMock()
            gc._session.request.return_value.json.return_value = {
                "responses": [
                    {
                        "id": "0",
                        "status": 200,
                        "body": {
                            "value": [{"userPrincipalName": "primary@domain.com"}]
                        },
                    }
                ]
            }
            gc._session.request.return_value.raise_for_status = MagicMock()
            result = gc.fetch_primary_user_upns(["device-1"])
            assert result == {"device-1": "primary@domain.com"}


class TestParseGraphDatetime:
    def test_parses_zulu(self) -> None:
        dt = _parse_graph_datetime("2024-01-15T12:00:00Z")
        assert dt is not None
        assert dt.year == 2024


class TestEnvStatusName:
    def test_empty_uses_builtin_and_auto_create(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            name, auto = _env_status_name("SNIPEIT_DEFAULT_STATUS", "Ready to Deploy")
        assert name == "Ready to Deploy"
        assert auto is True

    def test_custom_name_disables_auto_create(self) -> None:
        with patch.dict(
            os.environ,
            {"SNIPEIT_DEFAULT_STATUS": "Deployed"},
            clear=True,
        ):
            name, auto = _env_status_name("SNIPEIT_DEFAULT_STATUS", "Ready to Deploy")
        assert name == "Deployed"
        assert auto is False


class TestStatusUnavailable:
    def test_missing_without_auto_create_blocks(self) -> None:
        assert _status_unavailable(None, auto_create=False, dry_run=False) is True

    def test_missing_with_auto_create_dry_run_allows(self) -> None:
        assert _status_unavailable(None, auto_create=True, dry_run=True) is False

    def test_present_always_ok(self) -> None:
        assert _status_unavailable(5, auto_create=False, dry_run=False) is False


class TestSyncConfigStatusAutoCreate:
    def test_defaults_enable_auto_create(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
                "SNIPEIT_URL": "https://snipe.example/api/v1",
                "SNIPEIT_API_TOKEN": "tok",
            },
            clear=True,
        ):
            cfg = SyncConfig.from_env()
        assert cfg.auto_create_default_status is True
        assert cfg.auto_create_pending_autopilot is True
        assert cfg.default_status_name == "Ready to Deploy"

    def test_custom_status_name_disables_auto_create(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
                "SNIPEIT_URL": "https://snipe.example/api/v1",
                "SNIPEIT_API_TOKEN": "tok",
                "SNIPEIT_STATUS_ARCHIVED": "Retired",
            },
            clear=True,
        ):
            cfg = SyncConfig.from_env()
        assert cfg.status_archived == "Retired"
        assert cfg.auto_create_archived is False

    def test_skip_flag_disables_all_auto_create(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
                "SNIPEIT_URL": "https://snipe.example/api/v1",
                "SNIPEIT_API_TOKEN": "tok",
                "SNIPEIT_SKIP_STATUS_AUTO_CREATE": "true",
            },
            clear=True,
        ):
            cfg = SyncConfig.from_env()
        assert cfg.auto_create_default_status is False
        assert cfg.auto_create_pending_autopilot is False


class TestGetOrCreateStatusId:
    _SNIPE_ENV = {
        "SNIPEIT_URL": "https://snipe.example.com/api/v1",
        "SNIPEIT_API_TOKEN": "token",
    }

    def test_returns_existing_without_post(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._status_cache["Ready to Deploy"] = 42
            assert (
                snipe.get_or_create_status_id(
                    "Ready to Deploy",
                    create_if_missing=True,
                )
                == 42
            )

    def test_creates_when_missing(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._iter_rows = MagicMock(return_value=iter([]))  # type: ignore[method-assign]
            snipe._post = MagicMock(  # type: ignore[method-assign]
                return_value={"payload": {"id": 99, "name": "Pending Autopilot"}}
            )
            status_id = snipe.get_or_create_status_id(
                "Pending Autopilot",
                status_type="pending",
                create_if_missing=True,
            )
            assert status_id == 99
            snipe._post.assert_called_once_with(
                "/statuslabels",
                {"name": "Pending Autopilot", "type": "pending"},
            )

    def test_does_not_create_when_disabled(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._iter_rows = MagicMock(return_value=iter([]))  # type: ignore[method-assign]
            snipe._post = MagicMock()  # type: ignore[method-assign]
            assert (
                snipe.get_or_create_status_id(
                    "Archived",
                    create_if_missing=False,
                )
                is None
            )
            snipe._post.assert_not_called()

    def test_dry_run_logs_without_post(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._iter_rows = MagicMock(return_value=iter([]))  # type: ignore[method-assign]
            snipe._post = MagicMock()  # type: ignore[method-assign]
            assert (
                snipe.get_or_create_status_id(
                    "Archived",
                    status_type="archived",
                    create_if_missing=True,
                    dry_run=True,
                )
                is None
            )
            snipe._post.assert_not_called()


class TestSyncConfigUserSync:
    def test_defaults_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
                "SNIPEIT_URL": "https://snipe.example/api/v1",
                "SNIPEIT_API_TOKEN": "tok",
            },
            clear=True,
        ):
            cfg = SyncConfig.from_env()
        assert cfg.user_sync_enabled is False
        assert cfg.user_sync_group_ids == []
        assert cfg.company_from_user is False

    def test_enabled_parses_group_ids_and_toggles(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "t",
                "AZURE_CLIENT_ID": "c",
                "AZURE_CLIENT_SECRET": "s",
                "SNIPEIT_URL": "https://snipe.example/api/v1",
                "SNIPEIT_API_TOKEN": "tok",
                "ENTRA_USER_SYNC_ENABLED": "true",
                "ENTRA_USER_SYNC_GROUP_IDS": " g1 , g2 ",
                "ENTRA_USER_SYNC_CREATE_DEPARTMENT": "false",
                "SNIPEIT_COMPANY_FROM_USER": "true",
            },
            clear=True,
        ):
            cfg = SyncConfig.from_env()
        assert cfg.user_sync_enabled is True
        assert cfg.user_sync_group_ids == ["g1", "g2"]
        assert cfg.user_sync_create_company is True
        assert cfg.user_sync_create_department is False
        assert cfg.user_sync_create_location is True
        assert cfg.company_from_user is True


class TestFetchEntraGroupUsers:
    def test_no_groups_returns_empty(self) -> None:
        g = MagicMock()
        assert fetch_entra_group_users(g, []) == []
        g.get_paginated.assert_not_called()

    def test_dedupes_across_groups(self) -> None:
        g = MagicMock()
        g.get_paginated.side_effect = [
            [{"id": "u1", "userPrincipalName": "a@domain.com"}],
            [{"id": "u1", "userPrincipalName": "a@domain.com"}, {"id": "u2"}],
        ]
        out = fetch_entra_group_users(g, ["g1", "g2"])
        assert {u["id"] for u in out} == {"u1", "u2"}
        assert g.get_paginated.call_count == 2
        assert "microsoft.graph.user" in g.get_paginated.call_args_list[0][0][0]

    def test_403_raises_runtime_error(self) -> None:
        g = MagicMock()

        def boom(_url: str) -> list[dict]:
            resp = requests.Response()
            resp.status_code = 403
            raise requests.HTTPError(response=resp)

        g.get_paginated.side_effect = boom
        with pytest.raises(RuntimeError, match="403 Forbidden"):
            fetch_entra_group_users(g, ["g1"])


class TestSnipeCompanyDepartmentLocation:
    _SNIPE_ENV = {
        "SNIPEIT_URL": "https://snipe.example.com/api/v1",
        "SNIPEIT_API_TOKEN": "token",
    }

    def test_get_or_create_company_matches_existing(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._session = MagicMock()
            snipe._session.get.return_value.json.return_value = {
                "rows": [{"id": 3, "name": "Acme Inc"}]
            }
            snipe._session.get.return_value.raise_for_status = MagicMock()
            assert snipe.get_or_create_company("acme inc") == 3
            snipe._session.post.assert_not_called()

    def test_get_or_create_department_creates_with_company(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._iter_rows = MagicMock(return_value=iter([]))  # type: ignore[method-assign]
            snipe._post = MagicMock(  # type: ignore[method-assign]
                return_value={"payload": {"id": 8, "name": "Engineering"}}
            )
            dept_id = snipe.get_or_create_department("Engineering", 3)
            assert dept_id == 8
            snipe._post.assert_called_once_with(
                "/departments", {"name": "Engineering", "company_id": 3}
            )

    def test_get_or_create_location_by_name_creates(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._iter_rows = MagicMock(return_value=iter([]))  # type: ignore[method-assign]
            snipe._post = MagicMock(  # type: ignore[method-assign]
                return_value={"payload": {"id": 12, "name": "HQ"}}
            )
            assert snipe.get_or_create_location_by_name("HQ") == 12
            snipe._post.assert_called_once_with("/locations", {"name": "HQ"})


class TestFindEntraUserRow:
    _SNIPE_ENV = {
        "SNIPEIT_URL": "https://snipe.example.com/api/v1",
        "SNIPEIT_API_TOKEN": "token",
    }

    def test_matches_by_email(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._session = MagicMock()
            snipe._session.get.return_value.json.return_value = {
                "rows": [{"id": 5, "email": "user@domain.com"}]
            }
            snipe._session.get.return_value.raise_for_status = MagicMock()
            row = snipe.find_entra_user_row("user@domain.com", "entra-obj-1")
            assert row == {"id": 5, "email": "user@domain.com"}

    def test_falls_back_to_employee_num(self) -> None:
        with patch.dict(os.environ, self._SNIPE_ENV, clear=False):
            snipe = SnipeITClient(_test_config())
            snipe._session = MagicMock()
            snipe._session.get.return_value.raise_for_status = MagicMock()
            snipe._session.get.return_value.json.side_effect = [
                {"rows": []},
                {"rows": [{"id": 6, "employee_num": "entra-obj-1"}]},
            ]
            row = snipe.find_entra_user_row("user@domain.com", "entra-obj-1")
            assert row == {"id": 6, "employee_num": "entra-obj-1"}


class TestBuildEntraUserPayload:
    def test_create_includes_password_and_link(self) -> None:
        user = {
            "id": "entra-1",
            "userPrincipalName": "jdoe@domain.com",
            "mail": "jdoe@domain.com",
            "givenName": "Jane",
            "surname": "Doe",
            "jobTitle": "Engineer",
        }
        payload = _build_entra_user_payload(
            user, company_id=1, department_id=2, location_id=3, for_create=True
        )
        assert payload["username"] == "jdoe@domain.com"
        assert payload["employee_num"] == "entra-1"
        assert payload["company_id"] == 1
        assert payload["department_id"] == 2
        assert payload["location_id"] == 3
        assert payload["password"] == payload["password_confirmation"]
        assert len(payload["password"]) > 8

    def test_update_omits_password(self) -> None:
        user = {"id": "entra-2", "userPrincipalName": "asmith@domain.com"}
        payload = _build_entra_user_payload(
            user, company_id=None, department_id=None, location_id=None, for_create=False
        )
        assert "password" not in payload
        assert payload["employee_num"] == "entra-2"

    def test_disabled_account_deactivated(self) -> None:
        user = {"id": "e3", "userPrincipalName": "x@domain.com", "accountEnabled": False}
        payload = _build_entra_user_payload(
            user, company_id=None, department_id=None, location_id=None, for_create=False
        )
        assert payload["activated"] == 0


class TestSyncEntraUser:
    def test_skips_when_no_upn_or_mail(self) -> None:
        snipe = MagicMock()
        outcome = sync_entra_user(snipe, {"id": "e1"}, _test_config())
        assert outcome == UserSyncOutcome.SKIPPED_NO_UPN
        snipe.find_entra_user_row.assert_not_called()

    def test_creates_new_user_with_resolved_lookups(self) -> None:
        snipe = MagicMock()
        snipe.get_or_create_company.return_value = 10
        snipe.get_or_create_department.return_value = 20
        snipe.get_or_create_location_by_name.return_value = 30
        snipe.find_entra_user_row.return_value = None
        snipe.create_user.return_value = {"id": 99}
        user = {
            "id": "e-100",
            "userPrincipalName": "new@domain.com",
            "mail": "new@domain.com",
            "companyName": "Acme",
            "department": "Sales",
            "officeLocation": "HQ",
        }
        outcome = sync_entra_user(snipe, user, _test_config(), dry_run=False)
        assert outcome == UserSyncOutcome.CREATED
        snipe.get_or_create_company.assert_called_once_with("Acme", dry_run=False)
        snipe.get_or_create_department.assert_called_once_with("Sales", 10, dry_run=False)
        snipe.get_or_create_location_by_name.assert_called_once_with("HQ", dry_run=False)
        create_payload = snipe.create_user.call_args[0][0]
        assert create_payload["company_id"] == 10
        assert create_payload["department_id"] == 20
        assert create_payload["location_id"] == 30

    def test_updates_existing_user(self) -> None:
        snipe = MagicMock()
        snipe.get_or_create_company.return_value = None
        snipe.get_or_create_department.return_value = None
        snipe.get_or_create_location_by_name.return_value = None
        snipe.find_entra_user_row.return_value = {"id": 42}
        snipe.update_user.return_value = True
        user = {"id": "e-101", "userPrincipalName": "existing@domain.com"}
        outcome = sync_entra_user(snipe, user, _test_config(), dry_run=False)
        assert outcome == UserSyncOutcome.UPDATED
        snipe.update_user.assert_called_once()
        assert snipe.update_user.call_args[0][0] == 42
        snipe.create_user.assert_not_called()

    def test_dry_run_creates_nothing(self) -> None:
        snipe = MagicMock()
        snipe.get_or_create_company.return_value = None
        snipe.get_or_create_department.return_value = None
        snipe.get_or_create_location_by_name.return_value = None
        snipe.find_entra_user_row.return_value = None
        user = {"id": "e-102", "userPrincipalName": "dry@domain.com"}
        outcome = sync_entra_user(snipe, user, _test_config(), dry_run=True)
        assert outcome == UserSyncOutcome.DRY_RUN_CREATE
        snipe.create_user.assert_not_called()


class TestSyncEntraUsers:
    def test_disabled_returns_zero_counts_without_fetch(self) -> None:
        graph = MagicMock()
        snipe = MagicMock()
        counts = sync_entra_users(graph, snipe, _test_config(user_sync_enabled=False))
        assert counts[UserSyncOutcome.CREATED] == 0
        graph.get_paginated.assert_not_called()

    def test_enabled_without_group_ids_skips(self) -> None:
        graph = MagicMock()
        snipe = MagicMock()
        counts = sync_entra_users(
            graph, snipe, _test_config(user_sync_enabled=True, user_sync_group_ids=[])
        )
        assert counts[UserSyncOutcome.CREATED] == 0
        graph.get_paginated.assert_not_called()

    def test_enabled_processes_group_members(self) -> None:
        graph = MagicMock()
        graph.get_paginated.return_value = [
            {"id": "e1", "userPrincipalName": "one@domain.com"},
            {"id": "e2", "userPrincipalName": "two@domain.com"},
        ]
        snipe = MagicMock()
        snipe.get_or_create_company.return_value = None
        snipe.get_or_create_department.return_value = None
        snipe.get_or_create_location_by_name.return_value = None
        snipe.find_entra_user_row.return_value = None
        snipe.create_user.return_value = {"id": 1}
        counts = sync_entra_users(
            graph,
            snipe,
            _test_config(user_sync_enabled=True, user_sync_group_ids=["g1"]),
        )
        assert counts[UserSyncOutcome.CREATED] == 2


class TestCompanyFromUser:
    def test_company_follows_checked_out_user(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = None
        snipe.get_or_create_manufacturer.return_value = 1
        snipe.get_or_create_model.return_value = 2
        snipe.get_user_id.return_value = 5
        snipe.get_user_company_id.return_value = 77
        snipe.create_asset.return_value = {"id": 11}
        config = _test_config(company_from_user=True, company_id=1)
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "manufacturer": "Dell",
            "model": "XPS",
            "userPrincipalName": "user@domain.com",
        }
        outcome = sync_device(
            snipe, dev, category_id=1, default_status_id=2, config=config, dry_run=False
        )
        assert outcome == SyncOutcome.CREATED
        snipe.get_user_company_id.assert_called_once_with(5)
        create_payload = snipe.create_asset.call_args[0][0]
        assert create_payload["company_id"] == 77

    def test_disabled_uses_static_company_id(self) -> None:
        snipe = MagicMock()
        snipe.ensure_asset_for_sync.return_value = None
        snipe.get_or_create_manufacturer.return_value = 1
        snipe.get_or_create_model.return_value = 2
        snipe.get_user_id.return_value = 5
        snipe.create_asset.return_value = {"id": 11}
        config = _test_config(company_from_user=False, company_id=9)
        dev = {
            "deviceName": "pc",
            "serialNumber": "SN1",
            "manufacturer": "Dell",
            "model": "XPS",
            "userPrincipalName": "user@domain.com",
        }
        sync_device(
            snipe, dev, category_id=1, default_status_id=2, config=config, dry_run=False
        )
        snipe.get_user_company_id.assert_not_called()
        create_payload = snipe.create_asset.call_args[0][0]
        assert create_payload["company_id"] == 9
