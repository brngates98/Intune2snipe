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
    _assigned_user_id,
    _build_asset_payload,
    _device_user_upn,
    _format_summary,
    _managed_devices_url,
    _parse_group_ids,
    _parse_graph_datetime,
    _upn_location_prefix,
    fetch_group_device_ids,
    fetch_managed_devices,
    normalize_upn,
    sync_device,
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
        assert "OS 11" in payload["notes"]


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
        snipe.find_asset_by_serial.return_value = None
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
        snipe.find_asset_by_serial.assert_not_called()

    def test_dry_run_create(self) -> None:
        snipe = MagicMock()
        snipe.find_asset_by_serial.return_value = None
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
        snipe.find_asset_by_serial.return_value = {
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
        snipe.find_asset_by_serial.return_value = {
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
        snipe.find_asset_by_serial.return_value = {
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
