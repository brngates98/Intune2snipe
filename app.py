#!/usr/bin/env python3
"""Sync Intune managed devices to Snipe-IT.

Fetches devices from Microsoft Graph (Intune), optionally filtered by
platform and Azure AD group membership, then creates or updates
corresponding assets in Snipe-IT.

API references (validate behavior against current docs):
- Microsoft Graph — List managedDevices:
  https://learn.microsoft.com/en-us/graph/api/intune-devices-manageddevice-list
- Microsoft Graph — List group members (OData cast to device):
  https://learn.microsoft.com/en-us/graph/api/group-list-members
- Microsoft Graph — JSON batching:
  https://learn.microsoft.com/en-us/graph/json-batching
- Microsoft Graph — List windowsAutopilotDeviceIdentities:
  https://learn.microsoft.com/en-us/graph/api/intune-enrollment-windowsautopilotdeviceidentity-list
- Snipe-IT REST API — Restore hardware:
  https://snipe-it.readme.io/reference/hardwareidrestore
- Snipe-IT REST API — Users index (email / username query params):
  https://snipe-it.readme.io/reference/users
- Snipe-IT REST API — Hardware checkout (user / location):
  https://snipe-it.readme.io/reference/hardware-checkout
- Snipe-IT REST API — Status labels:
  https://snipe-it.readme.io/reference/statuslabels-1

Usage:
    python3 app.py --dry-run --platform windows
    python3 app.py --dry-run --groups "group-id-1,group-id-2"
    python3 app.py --platform all

Dependencies: requests, msal
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterator
from urllib.parse import quote, urlencode

import requests
from msal import ConfidentialClientApplication
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── LOGGING ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("intune2snipe")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = 30
GRAPH_TOKEN_SKEW_SECONDS = 300
GRAPH_BATCH_SIZE = 20
SNIPE_PAGE_SIZE = 200

GUID_PREFIX = re.compile(r"^[0-9a-f]{32}")

MANAGED_DEVICE_SELECT = (
    "id,deviceName,serialNumber,manufacturer,model,userPrincipalName,emailAddress,"
    "operatingSystem,azureADDeviceId,osVersion,complianceState,lastSyncDateTime,"
    "managedDeviceOwnerType,imei,meid,wiFiMacAddress,managementState"
)

PLATFORM_ODATA_FILTERS: dict[str, str] = {
    "windows": "operatingSystem eq 'Windows'",
    "ios": "operatingSystem eq 'iOS'",
    "android": "operatingSystem eq 'Android'",
    "macos": "operatingSystem eq 'macOS'",
}

RETIRING_MANAGEMENT_STATES = frozenset({
    "retirePending",
    "retireIssued",
    "retireFailed",
    "wipePending",
    "wipeIssued",
    "wipeFailed",
    "deletePending",
    "deleteIssued",
})

AUTOPILOT_PENDING_ENROLLMENT_STATES = frozenset({
    "pendingReset",
    "notContacted",
    "failed",
    "blocked",
})

AUTOPILOT_URL = (
    "https://graph.microsoft.com/v1.0/deviceManagement/windowsAutopilotDeviceIdentities"
)

# Intune managedDevice property -> env var holding Snipe custom-field DB column name
BUILTIN_CUSTOM_FIELD_ENV: dict[str, str] = {
    "id": "SNIPEIT_CF_INTUNE_DEVICE_ID",
    "azureADDeviceId": "SNIPEIT_CF_AZURE_AD_DEVICE_ID",
    "osVersion": "SNIPEIT_CF_OS_VERSION",
    "lastSyncDateTime": "SNIPEIT_CF_LAST_INTUNE_SYNC",
    "imei": "SNIPEIT_CF_IMEI",
    "meid": "SNIPEIT_CF_MEID",
    "wiFiMacAddress": "SNIPEIT_CF_WIFI_MAC",
    "complianceState": "SNIPEIT_CF_COMPLIANCE_STATE",
}

AUTOPILOT_CUSTOM_FIELD_ENV: dict[str, str] = {
    "enrollmentState": "SNIPEIT_CF_AUTOPILOT_ENROLLMENT_STATE",
    "lastContactedDateTime": "SNIPEIT_CF_AUTOPILOT_LAST_CONTACTED",
}

BUILTIN_DEFAULT_STATUS = "Ready to Deploy"
BUILTIN_STATUS_PENDING_AUTOPILOT = "Pending Autopilot"
BUILTIN_STATUS_PENDING_RETIRE = "Pending Retire"
BUILTIN_STATUS_ARCHIVED = "Archived"

# Snipe-IT status label ``type`` for built-in default names (see POST /statuslabels).
BUILTIN_STATUS_TYPES: dict[str, str] = {
    BUILTIN_DEFAULT_STATUS: "deployable",
    BUILTIN_STATUS_PENDING_AUTOPILOT: "pending",
    BUILTIN_STATUS_PENDING_RETIRE: "pending",
    BUILTIN_STATUS_ARCHIVED: "archived",
}


class SnipeAPIError(Exception):
    """Snipe-IT returned HTTP 200 with status=error in the JSON body."""


def _http_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _parse_group_ids(env_val: str | None) -> list[str]:
    if not env_val:
        return []
    return [gid.strip() for gid in env_val.split(",") if gid.strip()]


def _parse_json_env(name: str) -> dict[str, str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("Invalid JSON in %s: %s", name, exc)
        return {}
    if not isinstance(parsed, dict):
        log.warning("%s must be a JSON object", name)
        return {}
    return {str(k): str(v) for k, v in parsed.items() if v}


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _parse_int_env(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("Invalid integer for %s=%r", name, raw)
        return default


def _env_status_name(env_key: str, builtin_default: str) -> tuple[str, bool]:
    """Return status label name and whether missing labels may be auto-created."""
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return builtin_default, True
    return raw, False


def _builtin_status_type(name: str) -> str:
    return BUILTIN_STATUS_TYPES.get(name, "deployable")


@dataclass
class SyncConfig:
    checkout_mode: str = "user"
    location_prefix_len: int = 3
    use_primary_user: bool = False
    company_id: int | None = None
    stale_days: int | None = None
    sync_state_file: str | None = None
    include_deleted_assets: bool = False
    checkout_on_create: bool = True
    custom_fields: dict[str, str] = field(default_factory=dict)
    compliance_status_map: dict[str, str] = field(default_factory=dict)
    default_status_name: str = "Ready to Deploy"
    checkout_status_name: str | None = None
    checkin_status_name: str | None = None
    skip_autopilot: bool = False
    restore_deleted_assets: bool = True
    lifecycle_reconciliation: bool = True
    status_pending_autopilot: str = "Pending Autopilot"
    status_pending_retire: str = "Pending Retire"
    status_archived: str = "Archived"
    auto_create_default_status: bool = True
    auto_create_pending_autopilot: bool = True
    auto_create_pending_retire: bool = True
    auto_create_archived: bool = True

    @classmethod
    def from_env(cls, *, use_primary_user_cli: bool | None = None) -> SyncConfig:
        checkout_status = os.getenv("SNIPEIT_CHECKOUT_STATUS", "").strip() or None
        checkin_status = os.getenv("SNIPEIT_CHECKIN_STATUS", "").strip() or None
        default_name, auto_default = _env_status_name(
            "SNIPEIT_DEFAULT_STATUS", BUILTIN_DEFAULT_STATUS
        )
        pending_ap, auto_ap = _env_status_name(
            "SNIPEIT_STATUS_PENDING_AUTOPILOT", BUILTIN_STATUS_PENDING_AUTOPILOT
        )
        pending_retire, auto_retire = _env_status_name(
            "SNIPEIT_STATUS_PENDING_RETIRE", BUILTIN_STATUS_PENDING_RETIRE
        )
        archived_name, auto_archived = _env_status_name(
            "SNIPEIT_STATUS_ARCHIVED", BUILTIN_STATUS_ARCHIVED
        )
        auto_create_enabled = not _parse_bool_env("SNIPEIT_SKIP_STATUS_AUTO_CREATE", False)
        use_primary = (
            use_primary_user_cli
            if use_primary_user_cli is not None
            else _parse_bool_env("GRAPH_USE_PRIMARY_USER", False)
        )
        custom_fields = _build_custom_field_map()
        return cls(
            checkout_mode=_normalize_checkout_mode(
                os.getenv("SNIPEIT_CHECKOUT_MODE", "user")
            ),
            location_prefix_len=_location_prefix_length(),
            use_primary_user=use_primary,
            company_id=_parse_int_env("SNIPEIT_COMPANY_ID"),
            stale_days=_parse_int_env("SNIPEIT_STALE_DAYS"),
            sync_state_file=os.getenv("SYNC_STATE_FILE", "").strip() or None,
            include_deleted_assets=_parse_bool_env("SNIPEIT_INCLUDE_DELETED_ASSETS", False),
            checkout_on_create=not _parse_bool_env("SNIPEIT_SKIP_CHECKOUT_ON_CREATE", False),
            custom_fields=custom_fields,
            compliance_status_map=_parse_json_env("SNIPEIT_COMPLIANCE_STATUS_MAP"),
            default_status_name=default_name,
            checkout_status_name=checkout_status,
            checkin_status_name=checkin_status,
            skip_autopilot=_parse_bool_env("SNIPEIT_SKIP_AUTOPILOT", False),
            restore_deleted_assets=not _parse_bool_env(
                "SNIPEIT_SKIP_RESTORE_DELETED", False
            ),
            lifecycle_reconciliation=not _parse_bool_env(
                "SNIPEIT_SKIP_LIFECYCLE_RECONCILIATION", False
            ),
            status_pending_autopilot=pending_ap,
            status_pending_retire=pending_retire,
            status_archived=archived_name,
            auto_create_default_status=auto_create_enabled and auto_default,
            auto_create_pending_autopilot=auto_create_enabled and auto_ap,
            auto_create_pending_retire=auto_create_enabled and auto_retire,
            auto_create_archived=auto_create_enabled and auto_archived,
        )


def _build_custom_field_map() -> dict[str, str]:
    """Map Intune property names to Snipe-IT custom field DB column names."""
    mapping: dict[str, str] = {}
    for intune_key, env_name in BUILTIN_CUSTOM_FIELD_ENV.items():
        col = os.getenv(env_name, "").strip()
        if col:
            mapping[intune_key] = col
    mapping.update(_parse_json_env("SNIPEIT_CUSTOM_FIELDS"))
    for ap_key, env_name in AUTOPILOT_CUSTOM_FIELD_ENV.items():
        col = os.getenv(env_name, "").strip()
        if col:
            mapping[f"_autopilot_{ap_key}"] = col
    return mapping


# ─── CLIENTS ──────────────────────────────────────────────────────────────────


class GraphClient:
    """Microsoft Graph API client using MSAL client credentials."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float | None = None
        self._tenant_id = os.getenv("AZURE_TENANT_ID", "")
        self._client_id = os.getenv("AZURE_CLIENT_ID", "")
        self._client_secret = os.getenv("AZURE_CLIENT_SECRET", "")
        self._app: ConfidentialClientApplication | None = None
        self._session = _http_session()

    def _ensure_auth(self) -> None:
        now = time.time()
        if (
            self._token
            and self._token_expires_at is not None
            and now < self._token_expires_at - GRAPH_TOKEN_SKEW_SECONDS
        ):
            return

        self._token = None
        self._token_expires_at = None
        if not self._tenant_id or not self._client_id or not self._client_secret:
            raise RuntimeError(
                "Azure credentials not configured. Set AZURE_TENANT_ID, "
                "AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET environment variables."
            )
        self._app = ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
        )
        result = self._app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(
                f"Failed to acquire Graph access token: {result.get('error_description', result)}"
            )
        self._token = result["access_token"]
        expires_in = int(result.get("expires_in", 3600))
        self._token_expires_at = time.time() + expires_in
        log.info(
            "Authenticated with Microsoft Graph (access token expires in %s seconds)",
            expires_in,
        )

    def _refresh_token(self) -> None:
        self._token = None
        self._token_expires_at = None
        self._ensure_auth()

    def _headers(self) -> dict[str, str]:
        self._ensure_auth()
        assert self._token is not None
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        resp = self._session.request(
            method, url, headers=self._headers(), timeout=DEFAULT_TIMEOUT, **kwargs
        )
        if resp.status_code == 401:
            self._refresh_token()
            resp = self._session.request(
                method, url, headers=self._headers(), timeout=DEFAULT_TIMEOUT, **kwargs
            )
        resp.raise_for_status()
        return resp

    def get_paginated(self, url: str) -> list[dict]:
        """Fetch all pages from a Graph API endpoint."""
        results: list[dict] = []
        while url:
            data = self._request("GET", url).json()
            results.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return results

    def fetch_primary_user_upns(self, managed_device_ids: list[str]) -> dict[str, str]:
        """Resolve primary user UPNs via beta ``/managedDevices/{id}/users`` ($batch)."""
        if not managed_device_ids:
            return {}

        upn_by_device: dict[str, str] = {}
        for i in range(0, len(managed_device_ids), GRAPH_BATCH_SIZE):
            chunk = managed_device_ids[i : i + GRAPH_BATCH_SIZE]
            requests_payload = [
                {
                    "id": str(idx),
                    "method": "GET",
                    "url": f"/beta/deviceManagement/managedDevices/{dev_id}/users",
                }
                for idx, dev_id in enumerate(chunk)
            ]
            batch_url = "https://graph.microsoft.com/v1.0/$batch"
            data = self._request(
                "POST", batch_url, json={"requests": requests_payload}
            ).json()
            for item in data.get("responses", []):
                req_id = int(item.get("id", -1))
                if req_id < 0 or req_id >= len(chunk):
                    continue
                device_id = chunk[req_id]
                if item.get("status") != 200:
                    log.debug(
                        "Primary user lookup failed for device %s: HTTP %s",
                        device_id,
                        item.get("status"),
                    )
                    continue
                body = item.get("body") or {}
                users = body.get("value") or []
                if not users:
                    continue
                user = users[0]
                upn = user.get("userPrincipalName") or user.get("mail")
                if upn:
                    upn_by_device[device_id] = upn

        log.info(
            "Resolved primary user for %d of %d device(s) via Graph batch",
            len(upn_by_device),
            len(managed_device_ids),
        )
        return upn_by_device

    def fetch_autopilot_by_serial(self) -> dict[str, dict]:
        """Index Windows Autopilot identities by serial number (lowercase key)."""
        by_serial: dict[str, dict] = {}
        try:
            records = self.get_paginated(AUTOPILOT_URL)
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                log.warning(
                    "403 Forbidden listing Autopilot devices: grant "
                    "DeviceManagementServiceConfig.Read.All (see Graph: "
                    "List windowsAutopilotDeviceIdentities)."
                )
            else:
                log.warning("Failed to fetch Autopilot devices: %s", exc)
            return by_serial
        for record in records:
            serial = (record.get("serialNumber") or "").strip()
            if not serial:
                continue
            by_serial[serial.casefold()] = record
        log.info("Loaded %d Windows Autopilot device(s) by serial", len(by_serial))
        return by_serial


class SnipeITClient:
    """Snipe-IT API client."""

    def __init__(self, config: SyncConfig) -> None:
        self._config = config
        self._base_url = os.getenv("SNIPEIT_URL", "").rstrip("/")
        self._token = os.getenv("SNIPEIT_API_TOKEN", "")
        if not self._base_url or not self._token:
            raise RuntimeError(
                "Snipe-IT credentials not configured. Set SNIPEIT_URL and "
                "SNIPEIT_API_TOKEN environment variables."
            )
        self._session = _http_session()
        self._category_cache: dict[str, int] = {}
        self._manufacturer_cache: dict[str, int] = {}
        self._model_cache: dict[str, int] = {}
        self._status_cache: dict[str, int] = {}
        self._user_cache: dict[str, int | None] = {}
        self._location_cache: dict[str, int | None] = {}
        self._checkout_status_id: int | None = None
        self._checkin_status_id: int | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _parse_snipe_response(self, data: dict) -> dict:
        if data.get("status") == "error":
            raise SnipeAPIError(str(data.get("messages", data)))
        return data

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._session.get(
            self._url(path),
            headers=self._headers(),
            params=params,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return self._parse_snipe_response(resp.json())

    def _post(self, path: str, payload: dict) -> dict:
        resp = self._session.post(
            self._url(path),
            headers=self._headers(),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return self._parse_snipe_response(resp.json())

    def _patch(self, path: str, payload: dict) -> dict:
        resp = self._session.patch(
            self._url(path),
            headers=self._headers(),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return self._parse_snipe_response(resp.json())

    def _iter_rows(self, path: str, params: dict | None = None) -> Iterator[dict]:
        base_params = dict(params or {})
        offset = 0
        while True:
            page_params = {**base_params, "offset": offset, "limit": SNIPE_PAGE_SIZE}
            data = self._get(path, page_params)
            rows = data.get("rows") or []
            if not rows:
                break
            yield from rows
            if len(rows) < SNIPE_PAGE_SIZE:
                break
            offset += SNIPE_PAGE_SIZE

    def checkout_status_id(self) -> int | None:
        if self._checkout_status_id is not None:
            return self._checkout_status_id
        name = self._config.checkout_status_name or self._config.default_status_name
        self._checkout_status_id = self.get_status_id(name)
        return self._checkout_status_id

    def checkin_status_id(self) -> int | None:
        if self._checkin_status_id is not None:
            return self._checkin_status_id
        name = (
            self._config.checkin_status_name
            or self._config.default_status_name
        )
        self._checkin_status_id = self.get_status_id(name)
        return self._checkin_status_id

    def _find_in_rows(
        self,
        path: str,
        params: dict,
        *,
        match_field: str,
        search: str,
        case_insensitive: bool = False,
    ) -> int | None:
        search_cf = search.casefold()
        for row in self._iter_rows(path, params):
            val = row.get(match_field)
            if val is None:
                continue
            if case_insensitive:
                if str(val).casefold() == search_cf:
                    return row["id"]
            elif val == search:
                return row["id"]
        return None

    def _find_exact(
        self,
        path: str,
        search: str,
        match_field: str = "name",
        *,
        case_insensitive: bool = False,
    ) -> int | None:
        return self._find_in_rows(
            path,
            {"search": search},
            match_field=match_field,
            search=search,
            case_insensitive=case_insensitive,
        )

    def get_or_create_category(self, name: str, *, dry_run: bool = False) -> int | None:
        if not name:
            return None
        if name in self._category_cache:
            return self._category_cache[name]
        cat_id = self._find_exact("/categories", name, case_insensitive=True)
        if cat_id:
            self._category_cache[name] = cat_id
            return cat_id
        if dry_run:
            return None
        resp = self._post("/categories", {"name": name, "category_type": "asset"})
        if resp.get("payload"):
            cat_id = resp["payload"]["id"]
            self._category_cache[name] = cat_id
            return cat_id
        cat_id = self._find_exact("/categories", name, case_insensitive=True)
        if cat_id:
            self._category_cache[name] = cat_id
            return cat_id
        log.warning("Could not create category '%s': %s", name, resp)
        return None

    def get_or_create_manufacturer(self, name: str, *, dry_run: bool = False) -> int | None:
        if not name:
            return None
        if name in self._manufacturer_cache:
            return self._manufacturer_cache[name]
        man_id = self._find_exact("/manufacturers", name, case_insensitive=True)
        if man_id:
            self._manufacturer_cache[name] = man_id
            return man_id
        if dry_run:
            return None
        resp = self._post("/manufacturers", {"name": name})
        if resp.get("payload"):
            man_id = resp["payload"]["id"]
            self._manufacturer_cache[name] = man_id
            return man_id
        man_id = self._find_exact("/manufacturers", name, case_insensitive=True)
        if man_id:
            self._manufacturer_cache[name] = man_id
            return man_id
        log.warning("Could not create manufacturer '%s': %s", name, resp)
        return None

    def get_or_create_model(
        self,
        model_number: str,
        manufacturer_id: int | None,
        category_id: int | None,
        *,
        dry_run: bool = False,
    ) -> int | None:
        if not model_number:
            return None
        if model_number in self._model_cache:
            return self._model_cache[model_number]
        model_cf = model_number.casefold()
        mod_id = self._find_in_rows(
            "/models",
            {"model_number": model_number},
            match_field="model_number",
            search=model_number,
            case_insensitive=True,
        )
        if mod_id is None:
            mod_id = self._find_exact(
                "/models", model_number, case_insensitive=True
            )
        if mod_id is None:
            for row in self._iter_rows("/models", {"search": model_number}):
                mn = row.get("model_number") or ""
                nm = row.get("name") or ""
                if mn.casefold() == model_cf or nm.casefold() == model_cf:
                    mod_id = row["id"]
                    break
        if mod_id:
            self._model_cache[model_number] = mod_id
            return mod_id
        if dry_run:
            return None
        resp = self._post("/models", {
            "name": model_number,
            "model_number": model_number,
            "manufacturer_id": manufacturer_id,
            "category_id": category_id,
        })
        if resp.get("payload"):
            mod_id = resp["payload"]["id"]
            self._model_cache[model_number] = mod_id
            return mod_id
        log.warning("Could not create model '%s': %s", model_number, resp)
        return None

    def _lookup_status_id(self, name: str) -> int | None:
        if name in self._status_cache:
            return self._status_cache[name]
        for row in self._iter_rows("/statuslabels"):
            if row.get("name") == name:
                self._status_cache[name] = row["id"]
                return row["id"]
        return None

    def get_status_id(self, name: str) -> int | None:
        status_id = self._lookup_status_id(name)
        if status_id is None:
            log.error("Status label '%s' not found", name)
        return status_id

    def get_or_create_status_id(
        self,
        name: str,
        *,
        status_type: str = "deployable",
        create_if_missing: bool = False,
        dry_run: bool = False,
    ) -> int | None:
        status_id = self._lookup_status_id(name)
        if status_id is not None:
            return status_id
        if not create_if_missing:
            return None
        if dry_run:
            log.info(
                "[DRY RUN] Would create status label '%s' (type=%s)",
                name,
                status_type,
            )
            return None
        try:
            resp = self._post("/statuslabels", {"name": name, "type": status_type})
        except (requests.RequestException, SnipeAPIError) as exc:
            log.error("Failed to create status label '%s': %s", name, exc)
            return None
        if resp.get("payload"):
            status_id = resp["payload"]["id"]
            self._status_cache[name] = status_id
            log.info("Created status label '%s' (id=%s, type=%s)", name, status_id, status_type)
            return status_id
        status_id = self._lookup_status_id(name)
        if status_id is not None:
            return status_id
        log.warning("Could not create status label '%s': %s", name, resp)
        return None

    def get_user_id(self, upn: str | None) -> int | None:
        if not upn:
            return None
        cache_key = upn.casefold()
        if cache_key in self._user_cache:
            return self._user_cache[cache_key]

        user_id: int | None = None
        if "@" in upn:
            for row in self._iter_rows("/users", {"email": upn}):
                em = row.get("email")
                if em and em.casefold() == cache_key:
                    user_id = row["id"]
                    break

        if user_id is None:
            for row in self._iter_rows("/users", {"username": upn}):
                un = row.get("username")
                if un and un.casefold() == cache_key:
                    user_id = row["id"]
                    break

        if user_id is None:
            log.warning(
                "No Snipe-IT user found with matching email or username for %s",
                upn,
            )
        self._user_cache[cache_key] = user_id
        return user_id

    def get_location_id(self, upn: str | None, prefix_len: int = 3) -> int | None:
        prefix = _upn_location_prefix(upn, prefix_len)
        if not prefix:
            return None
        cache_key = prefix.casefold()
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        location_id: int | None = None
        for row in self._iter_rows("/locations", {"search": prefix}):
            name = row.get("name") or ""
            if name.casefold().startswith(cache_key):
                location_id = row["id"]
                break

        if location_id is None:
            log.warning(
                "No Snipe-IT location found with name prefix '%s' for %s",
                prefix,
                upn,
            )
        self._location_cache[cache_key] = location_id
        return location_id

    def find_asset_by_serial(
        self, serial: str, *, include_deleted: bool = False
    ) -> dict | None:
        if not serial:
            return None
        path = f"/hardware/byserial/{quote(serial, safe='')}"
        params = {"deleted": "true"} if include_deleted else None
        try:
            data = self._get(path, params)
        except SnipeAPIError as exc:
            if _snipe_asset_not_found(exc):
                return None
            if include_deleted:
                return None
            raise
        asset = _extract_asset_row(data)
        if asset:
            return asset
        if include_deleted:
            return None
        return self.find_asset_by_serial(serial, include_deleted=True)

    def ensure_asset_for_sync(
        self, serial: str, *, config: SyncConfig
    ) -> dict | None:
        """Find asset by serial; optionally restore soft-deleted rows before sync."""
        include_deleted = (
            config.include_deleted_assets or config.restore_deleted_assets
        )
        asset = self.find_asset_by_serial(serial, include_deleted=include_deleted)
        if not asset:
            return None
        if config.restore_deleted_assets and _asset_is_deleted(asset):
            asset_id = asset.get("id")
            if asset_id is None:
                return asset
            if self.restore_asset(int(asset_id)):
                restored = self.find_asset_by_serial(serial, include_deleted=False)
                return restored or asset
        return asset

    def restore_asset(self, asset_id: int) -> bool:
        try:
            resp = self._post(f"/hardware/{asset_id}/restore", {})
        except (requests.RequestException, SnipeAPIError) as exc:
            log.error("Restore failed for asset %d: %s", asset_id, exc)
            return False
        if resp.get("status") == "success":
            log.info("Restored soft-deleted asset %d", asset_id)
            return True
        log.error("Restore failed for asset %d: %s", asset_id, resp)
        return False

    def apply_lifecycle_update(
        self,
        asset_id: int,
        *,
        status_id: int | None,
        notes: str,
        archived: bool = False,
    ) -> bool:
        payload: dict[str, Any] = {"notes": notes}
        if status_id is not None:
            payload["status_id"] = status_id
        if archived:
            payload["archived"] = 1
        try:
            data = self._patch(f"/hardware/{asset_id}", payload)
        except (requests.RequestException, SnipeAPIError) as exc:
            log.error("Lifecycle update failed for asset %d: %s", asset_id, exc)
            return False
        if data.get("status") == "success":
            return True
        log.error("Lifecycle update failed for asset %d: %s", asset_id, data)
        return False

    def create_asset(self, payload: dict) -> dict | None:
        try:
            resp = self._post("/hardware", payload)
        except SnipeAPIError as exc:
            log.error("Failed to create asset: %s", exc)
            return None
        if resp.get("status") == "success" and resp.get("payload"):
            return resp["payload"]
        log.error("Failed to create asset: %s", resp)
        return None

    def update_asset(self, asset_id: int, payload: dict) -> bool:
        try:
            data = self._patch(f"/hardware/{asset_id}", payload)
        except (requests.RequestException, SnipeAPIError) as e:
            log.error("Failed to update asset %d: %s", asset_id, e)
            return False
        if data.get("status") == "success":
            return True
        log.error("Failed to update asset %d: %s", asset_id, data)
        return False

    def checkout_asset(self, asset_id: int, user_id: int) -> bool:
        status_id = self.checkout_status_id()
        if status_id is None:
            log.error("Checkout status label not configured")
            return False
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        payload: dict[str, Any] = {
            "checkout_to_type": "user",
            "assigned_user": user_id,
            "checkout_at": now,
            "status_id": status_id,
        }
        try:
            resp = self._post(f"/hardware/{asset_id}/checkout", payload)
        except (requests.RequestException, SnipeAPIError) as e:
            log.error("Checkout failed for asset %d: %s", asset_id, e)
            return False
        if resp.get("status") == "success":
            return True
        log.error("Checkout failed for asset %d: %s", asset_id, resp)
        return False

    def checkout_asset_to_location(self, asset_id: int, location_id: int) -> bool:
        status_id = self.checkout_status_id()
        if status_id is None:
            log.error("Checkout status label not configured")
            return False
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        payload: dict[str, Any] = {
            "checkout_to_type": "location",
            "assigned_location": location_id,
            "checkout_at": now,
            "status_id": status_id,
        }
        try:
            resp = self._post(f"/hardware/{asset_id}/checkout", payload)
        except (requests.RequestException, SnipeAPIError) as e:
            log.error("Location checkout failed for asset %d: %s", asset_id, e)
            return False
        if resp.get("status") == "success":
            return True
        log.error("Location checkout failed for asset %d: %s", asset_id, resp)
        return False

    def checkin_asset(self, asset_id: int) -> bool:
        status_id = self.checkin_status_id()
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        payload: dict[str, Any] = {"checkin_at": now}
        if status_id is not None:
            payload["status_id"] = status_id
        try:
            resp = self._post(f"/hardware/{asset_id}/checkin", payload)
        except (requests.RequestException, SnipeAPIError) as e:
            log.error("Checkin failed for asset %d: %s", asset_id, e)
            return False
        if resp.get("status") == "success":
            return True
        log.error("Checkin failed for asset %d: %s", asset_id, resp)
        return False


# ─── SYNC LOGIC ───────────────────────────────────────────────────────────────


def _snipe_asset_not_found(exc: SnipeAPIError) -> bool:
    """Snipe returns HTTP 200 with status error when byserial finds no asset."""
    msg = str(exc).casefold()
    return "does not exist" in msg or "asset not found" in msg


def _asset_tag_for_create(device_name: str, serial: str) -> str | None:
    for candidate in (device_name, serial):
        tag = str(candidate or "").strip()
        if tag:
            return tag
    return None


def _extract_asset_row(data: dict) -> dict | None:
    rows = data.get("rows")
    if rows:
        return rows[0]
    if data.get("id"):
        return data
    payload = data.get("payload")
    if isinstance(payload, dict) and payload.get("id"):
        return payload
    return None


def _asset_is_deleted(asset: dict) -> bool:
    if asset.get("deleted_at"):
        return True
    deleted = asset.get("deleted")
    if deleted in (True, 1, "1"):
        return True
    return False


def _platform_includes_windows(platform: str) -> bool:
    return platform in {"windows", "all"}


def _is_windows_device(device: dict) -> bool:
    os_val = (device.get("operatingSystem") or "").lower()
    return os_val.startswith("windows")


def _device_platform_key(device: dict) -> str:
    os_val = (device.get("operatingSystem") or "").lower()
    if os_val.startswith("windows"):
        return "windows"
    if "android" in os_val:
        return "android"
    if "ios" in os_val:
        return "ios"
    if "mac" in os_val:
        return "macos"
    return "other"


def _state_entry_in_scope(entry: dict, platform: str) -> bool:
    if platform == "all":
        return True
    entry_platform = (entry.get("platform") or "").casefold()
    if not entry_platform:
        return platform == "windows"
    return entry_platform == platform.casefold()


def _enrich_device_autopilot(device: dict, autopilot: dict | None) -> None:
    if not autopilot:
        return
    for key in ("enrollmentState", "lastContactedDateTime", "managedDeviceId"):
        val = autopilot.get(key)
        if val is not None and val != "":
            device[f"_autopilot_{key}"] = val


def _autopilot_pending(ap_record: dict | None) -> bool:
    if not ap_record:
        return False
    state = (ap_record.get("enrollmentState") or "").casefold()
    return state in {s.casefold() for s in AUTOPILOT_PENDING_ENROLLMENT_STATES}


def normalize_upn(upn_raw: str | None) -> str | None:
    if not upn_raw:
        return None
    m = GUID_PREFIX.match(upn_raw)
    return upn_raw[m.end():] if m else upn_raw


def _normalize_checkout_mode(mode: str) -> str:
    normalized = mode.strip().casefold()
    if normalized == "location":
        return "location"
    return "user"


def _location_prefix_length() -> int:
    raw = os.getenv("SNIPEIT_LOCATION_PREFIX_LENGTH", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        log.warning("Invalid SNIPEIT_LOCATION_PREFIX_LENGTH=%r; using 3", raw)
        return 3


def _upn_location_prefix(upn: str | None, prefix_len: int) -> str | None:
    if not upn or "@" not in upn:
        return None
    local = upn.split("@", 1)[0]
    if not local:
        return None
    return local[:prefix_len]


def _parse_graph_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _device_user_upn(
    device: dict,
    primary_upns: dict[str, str],
    config: SyncConfig,
) -> str | None:
    device_id = device.get("id")
    if config.use_primary_user and device_id and device_id in primary_upns:
        upn = normalize_upn(primary_upns[device_id])
        if upn:
            return upn
    upn = normalize_upn(device.get("userPrincipalName"))
    if upn:
        return upn
    return normalize_upn(device.get("emailAddress"))


def _device_in_retire_state(device: dict) -> bool:
    state = device.get("managementState")
    return bool(state and state in RETIRING_MANAGEMENT_STATES)


def _device_is_stale(device: dict, stale_days: int) -> bool:
    last_sync = _parse_graph_datetime(device.get("lastSyncDateTime"))
    if last_sync is None:
        return False
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=stale_days)
    return last_sync < cutoff


def _resolve_status_id(
    snipe: SnipeITClient,
    device: dict,
    default_status_id: int,
    config: SyncConfig,
) -> int:
    compliance = (device.get("complianceState") or "").casefold()
    if compliance and config.compliance_status_map:
        mapped = config.compliance_status_map.get(compliance)
        if mapped:
            status_id = snipe.get_status_id(mapped)
            if status_id is not None:
                return status_id
    return default_status_id


def _custom_field_payload(device: dict, config: SyncConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for intune_key, snipe_col in config.custom_fields.items():
        if intune_key.startswith("_autopilot_"):
            value = device.get(intune_key)
        else:
            value = device.get(intune_key)
        if value is not None and value != "":
            payload[snipe_col] = value
    return payload


def _asset_notes(
    device: dict,
    man_name: str | None,
    mod_number: str | None,
    *,
    autopilot: dict | None = None,
    extra: str | None = None,
) -> str:
    parts = [f"Intune: {man_name or '?'} {mod_number or '?'}"]
    os_version = device.get("osVersion")
    if os_version:
        parts.append(f"OS {os_version}")
    last_sync = device.get("lastSyncDateTime")
    if last_sync:
        parts.append(f"last sync {last_sync}")
    mgmt = device.get("managementState")
    if mgmt:
        parts.append(f"managementState {mgmt}")
    if autopilot:
        ap_state = autopilot.get("enrollmentState")
        if ap_state:
            parts.append(f"Autopilot {ap_state}")
        ap_last = autopilot.get("lastContactedDateTime")
        if ap_last:
            parts.append(f"autopilot contacted {ap_last}")
    if extra:
        parts.append(extra)
    return " | ".join(parts)


def _build_asset_payload(
    device: dict,
    *,
    device_name: str,
    serial: str,
    man_id: int | None,
    mod_id: int,
    status_id: int,
    config: SyncConfig,
    man_name: str | None,
    mod_number: str | None,
    checkout_mode: str,
    checkout_target_id: int | None,
    for_create: bool,
    autopilot: dict | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": device_name,
        "model_id": mod_id,
        "notes": _asset_notes(device, man_name, mod_number, autopilot=autopilot),
    }
    if for_create:
        payload["serial"] = serial
        payload["status_id"] = status_id
        asset_tag = _asset_tag_for_create(device_name, serial)
        if asset_tag:
            payload["asset_tag"] = asset_tag
        if man_id is not None:
            payload["manufacturer_id"] = man_id
    else:
        payload["serial"] = serial
        payload["status_id"] = status_id
        if man_id is not None:
            payload["manufacturer_id"] = man_id

    if config.company_id is not None:
        payload["company_id"] = config.company_id

    owner = (device.get("managedDeviceOwnerType") or "").casefold()
    if owner == "personal":
        payload["byod"] = 1

    payload.update(_custom_field_payload(device, config))

    if for_create and config.checkout_on_create and checkout_target_id:
        if checkout_mode == "location":
            payload["assigned_location"] = checkout_target_id
        else:
            payload["assigned_user"] = checkout_target_id

    return payload


def load_sync_state(path: str | None) -> dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read sync state from %s: %s", path, exc)
        return {}


def save_sync_state(path: str | None, state: dict[str, Any]) -> None:
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except OSError as exc:
        log.warning("Could not write sync state to %s: %s", path, exc)


def fetch_group_device_ids(graph: GraphClient, group_ids: list[str]) -> set[str] | None:
    if not group_ids:
        return None
    device_ids: set[str] = set()
    for group_id in group_ids:
        if not group_id:
            continue
        try:
            url = (
                f"https://graph.microsoft.com/v1.0/groups/{group_id}"
                "/members/microsoft.graph.device"
            )
            devices = graph.get_paginated(url)
            for dev in devices:
                dev_id = dev.get("id")
                if dev_id:
                    device_ids.add(dev_id)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                log.warning("Group %s not found or not accessible", group_id)
            elif e.response is not None and e.response.status_code == 403:
                raise RuntimeError(
                    f"403 Forbidden accessing group {group_id}: grant an application "
                    "permission that can list group members, e.g. GroupMember.Read.All "
                    "or Group.Read.All (see Microsoft Graph: List group members)."
                ) from e
            else:
                log.error("Failed to fetch devices from group %s: %s", group_id, e)
    log.info("Found %d Azure AD devices from %d group(s)", len(device_ids), len(group_ids))
    return device_ids


def _managed_devices_url(platform: str) -> str:
    query: dict[str, str] = {"$select": MANAGED_DEVICE_SELECT}
    odata_filter = PLATFORM_ODATA_FILTERS.get(platform)
    if odata_filter:
        query["$filter"] = odata_filter
    return (
        "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices?"
        + urlencode(query, safe=",'")
    )


def _platform_matches_client(device: dict, platform: str) -> bool:
    os_val = (device.get("operatingSystem") or "").lower()
    if platform == "all":
        return True
    if platform == "windows":
        return os_val.startswith("windows")
    if platform == "android":
        return "android" in os_val
    if platform == "ios":
        return "ios" in os_val
    if platform == "macos":
        return "mac" in os_val
    return False


def fetch_managed_devices(
    graph: GraphClient, platform: str, group_ids: list[str] | None = None
) -> list[dict]:
    azure_ad_device_ids = fetch_group_device_ids(graph, group_ids or [])
    if azure_ad_device_ids is not None and len(azure_ad_device_ids) == 0:
        log.warning("No devices found in specified groups, nothing to sync")
        return []

    url = _managed_devices_url(platform)
    all_devices = graph.get_paginated(url)

    devices: list[dict] = []
    for dev in all_devices:
        if not _platform_matches_client(dev, platform):
            continue
        if azure_ad_device_ids is not None:
            device_id = dev.get("azureADDeviceId") or dev.get("azureActiveDeviceId")
            if device_id not in azure_ad_device_ids:
                continue
        devices.append(dev)
    return devices


class SyncOutcome(str, Enum):
    SKIPPED_NO_SERIAL = "skipped_no_serial"
    SKIPPED_NO_MODEL = "skipped_no_model"
    SKIPPED_STALE = "skipped_stale"
    DRY_RUN_UPDATE = "dry_run_update"
    DRY_RUN_CREATE = "dry_run_create"
    DRY_RUN_LIFECYCLE = "dry_run_lifecycle"
    UPDATED = "updated"
    UPDATE_FAILED = "update_failed"
    CREATED = "created"
    CREATE_FAILED = "create_failed"
    CREATED_CHECKOUT_FAILED = "created_checkout_failed"
    UPDATED_CHECKOUT_FAILED = "updated_checkout_failed"
    CHECKED_IN_STALE = "checked_in_stale"
    LIFECYCLE_PENDING_RETIRE = "lifecycle_pending_retire"
    LIFECYCLE_PENDING_AUTOPILOT = "lifecycle_pending_autopilot"
    LIFECYCLE_ARCHIVED = "lifecycle_archived"
    LIFECYCLE_FAILED = "lifecycle_failed"


def _assigned_user_id(asset: dict | None) -> int | None:
    if not asset:
        return None
    assigned = asset.get("assigned_to")
    if isinstance(assigned, dict):
        uid = assigned.get("id")
        return int(uid) if uid is not None else None
    return None


def _assigned_location_id(asset: dict | None) -> int | None:
    if not asset:
        return None
    loc = asset.get("location")
    if isinstance(loc, dict):
        lid = loc.get("id")
        return int(lid) if lid is not None else None
    assigned_loc = asset.get("assigned_location")
    if isinstance(assigned_loc, dict):
        lid = assigned_loc.get("id")
        return int(lid) if lid is not None else None
    lid = asset.get("location_id")
    return int(lid) if lid is not None else None


def _assigned_target_id(asset: dict | None, checkout_mode: str) -> int | None:
    if checkout_mode == "location":
        return _assigned_location_id(asset)
    return _assigned_user_id(asset)


def _resolve_checkout_target(
    snipe: SnipeITClient,
    upn: str | None,
    *,
    checkout_mode: str,
    location_prefix_len: int,
) -> tuple[str, int | None]:
    if checkout_mode == "location":
        return "location", snipe.get_location_id(upn, location_prefix_len)
    return "user", snipe.get_user_id(upn)


def _apply_checkout_if_needed(
    snipe: SnipeITClient,
    asset_id: int,
    checkout_mode: str,
    target_id: int | None,
    upn: str | None,
    existing: dict | None,
    *,
    dry_run: bool,
) -> bool:
    current = _assigned_target_id(existing, checkout_mode)

    if not upn:
        if current is not None:
            if dry_run:
                log.info(
                    "[DRY RUN] Would check in asset %d (no Intune primary user)",
                    asset_id,
                )
                return True
            if snipe.checkin_asset(asset_id):
                log.info("Checked in asset %d (no Intune primary user)", asset_id)
                return True
            return False
        return True

    if not target_id:
        return True
    if current == target_id:
        return True
    if checkout_mode == "location":
        target_label = f"location for {upn}"
    else:
        target_label = f"user {upn}"
    if dry_run:
        log.info("[DRY RUN] Would checkout asset %d to %s", asset_id, target_label)
        return True
    if checkout_mode == "location":
        ok = snipe.checkout_asset_to_location(asset_id, target_id)
    else:
        ok = snipe.checkout_asset(asset_id, target_id)
    if ok:
        log.info("Checked out asset %d to %s", asset_id, target_label)
    return ok


def _checkin_if_assigned(
    snipe: SnipeITClient,
    asset: dict,
    checkout_mode: str,
    *,
    dry_run: bool,
) -> bool:
    asset_id = asset.get("id")
    if asset_id is None:
        return True
    if _assigned_target_id(asset, checkout_mode) is None:
        return True
    if dry_run:
        log.info("[DRY RUN] Would check in asset %d (lifecycle)", asset_id)
        return True
    return snipe.checkin_asset(int(asset_id))


def _apply_lifecycle_to_asset(
    snipe: SnipeITClient,
    asset: dict,
    *,
    status_id: int | None,
    notes: str,
    archived: bool,
    checkout_mode: str,
    dry_run: bool,
) -> bool:
    asset_id = asset.get("id")
    if asset_id is None:
        return False
    if not _checkin_if_assigned(snipe, asset, checkout_mode, dry_run=dry_run):
        return False
    if dry_run:
        log.info(
            "[DRY RUN] Would set lifecycle on asset %d (archived=%s)",
            asset_id,
            archived,
        )
        return True
    return snipe.apply_lifecycle_update(
        int(asset_id),
        status_id=status_id,
        notes=notes,
        archived=archived,
    )


def _sync_device_retiring(
    snipe: SnipeITClient,
    device: dict,
    config: SyncConfig,
    *,
    default_status_id: int,
    status_ids: dict[str, int | None],
    autopilot: dict | None,
    dry_run: bool,
) -> SyncOutcome:
    device_name = device.get("deviceName", "unknown")
    serial = device.get("serialNumber")
    if not serial:
        return SyncOutcome.SKIPPED_NO_SERIAL

    existing = snipe.ensure_asset_for_sync(serial, config=config)
    if not existing:
        log.info(
            "Retiring device '%s' has no Snipe asset (serial %s); nothing to update",
            device_name,
            serial,
        )
        return SyncOutcome.LIFECYCLE_PENDING_RETIRE

    status_id = status_ids.get("pending_retire") or default_status_id
    notes = _asset_notes(
        device,
        device.get("manufacturer"),
        device.get("model"),
        autopilot=autopilot,
        extra=f"lifecycle: Intune {device.get('managementState')}",
    )
    ok = _apply_lifecycle_to_asset(
        snipe,
        existing,
        status_id=status_id,
        notes=notes,
        archived=False,
        checkout_mode=config.checkout_mode,
        dry_run=dry_run,
    )
    if dry_run:
        return SyncOutcome.DRY_RUN_LIFECYCLE
    return (
        SyncOutcome.LIFECYCLE_PENDING_RETIRE
        if ok
        else SyncOutcome.LIFECYCLE_FAILED
    )


def reconcile_missing_devices(
    snipe: SnipeITClient,
    config: SyncConfig,
    previous_state: dict[str, Any],
    current_intune_serials: set[str],
    autopilot_by_serial: dict[str, dict],
    *,
    platform: str,
    default_status_id: int,
    status_ids: dict[str, int | None],
    dry_run: bool,
) -> dict[SyncOutcome, int]:
    counts: dict[SyncOutcome, int] = {o: 0 for o in SyncOutcome}
    if not config.lifecycle_reconciliation or not config.sync_state_file:
        return counts

    for serial, entry in previous_state.items():
        if not isinstance(entry, dict):
            continue
        if serial in current_intune_serials:
            continue
        if not _state_entry_in_scope(entry, platform):
            continue

        ap_record = autopilot_by_serial.get(serial.casefold())
        is_windows = (entry.get("platform") or "").casefold() == "windows"
        if is_windows and _autopilot_pending(ap_record):
            outcome = SyncOutcome.LIFECYCLE_PENDING_AUTOPILOT
            status_id = status_ids.get("pending_autopilot")
            notes_extra = "lifecycle: absent from Intune; Autopilot pending re-deploy"
            archived = False
        else:
            outcome = SyncOutcome.LIFECYCLE_ARCHIVED
            status_id = status_ids.get("archived")
            notes_extra = "lifecycle: removed from Intune"
            archived = True

        existing = snipe.ensure_asset_for_sync(serial, config=config)
        if not existing:
            log.debug(
                "No Snipe asset for missing Intune serial %s; skipping reconciliation",
                serial,
            )
            continue

        pseudo_device = {
            "deviceName": entry.get("device_name") or serial,
            "lastSyncDateTime": entry.get("last_sync"),
            "managementState": entry.get("management_state"),
        }
        notes = _asset_notes(
            pseudo_device,
            entry.get("manufacturer"),
            entry.get("model"),
            autopilot=ap_record if is_windows else None,
            extra=notes_extra,
        )
        ok = _apply_lifecycle_to_asset(
            snipe,
            existing,
            status_id=status_id or default_status_id,
            notes=notes,
            archived=archived,
            checkout_mode=config.checkout_mode,
            dry_run=dry_run,
        )
        if dry_run:
            counts[SyncOutcome.DRY_RUN_LIFECYCLE] += 1
        elif ok:
            counts[outcome] += 1
            log.info(
                "Lifecycle %s for asset %d (serial %s)",
                outcome.value,
                existing["id"],
                serial,
            )
        else:
            counts[SyncOutcome.LIFECYCLE_FAILED] += 1

    return counts


def _status_unavailable(
    status_id: int | None,
    *,
    auto_create: bool,
    dry_run: bool,
) -> bool:
    """True when a required status label is missing and will not be created this run."""
    if status_id is not None:
        return False
    if auto_create and dry_run:
        return False
    return True


def _resolve_startup_status_id(
    snipe: SnipeITClient,
    name: str,
    *,
    auto_create: bool,
    dry_run: bool,
) -> int | None:
    return snipe.get_or_create_status_id(
        name,
        status_type=_builtin_status_type(name),
        create_if_missing=auto_create,
        dry_run=dry_run,
    )


def sync_device(
    snipe: SnipeITClient,
    device: dict,
    category_id: int,
    default_status_id: int,
    config: SyncConfig,
    *,
    dry_run: bool = False,
    primary_upns: dict[str, str] | None = None,
    autopilot: dict | None = None,
    status_ids: dict[str, int | None] | None = None,
) -> SyncOutcome:
    """Sync a single Intune device to Snipe-IT. Creates or updates as needed."""
    status_ids = status_ids or {}
    device_name = device.get("deviceName", "unknown")
    serial = device.get("serialNumber")
    if not serial:
        log.warning("Skipping '%s': no serial number", device_name)
        return SyncOutcome.SKIPPED_NO_SERIAL

    if _device_in_retire_state(device):
        return _sync_device_retiring(
            snipe,
            device,
            config,
            default_status_id=default_status_id,
            status_ids=status_ids,
            autopilot=autopilot,
            dry_run=dry_run,
        )

    primary_upns = primary_upns or {}
    upn = _device_user_upn(device, primary_upns, config)
    checkout_mode = config.checkout_mode
    _, checkout_target_id = _resolve_checkout_target(
        snipe,
        upn,
        checkout_mode=checkout_mode,
        location_prefix_len=config.location_prefix_len,
    )

    if config.stale_days and _device_is_stale(device, config.stale_days):
        existing = snipe.ensure_asset_for_sync(serial, config=config)
        if existing:
            asset_id = existing["id"]
            if dry_run:
                log.info("[DRY RUN] Would check in stale asset %d (%s)", asset_id, device_name)
                return SyncOutcome.SKIPPED_STALE
            if _assigned_target_id(existing, checkout_mode) is not None:
                if snipe.checkin_asset(asset_id):
                    log.info("Checked in stale asset %d: %s", asset_id, device_name)
                    return SyncOutcome.CHECKED_IN_STALE
                return SyncOutcome.UPDATED_CHECKOUT_FAILED
        log.info("Skipping stale device '%s' (no asset to check in)", device_name)
        return SyncOutcome.SKIPPED_STALE

    man_name = device.get("manufacturer")
    mod_number = device.get("model")
    man_id = snipe.get_or_create_manufacturer(man_name, dry_run=dry_run)
    mod_id = snipe.get_or_create_model(mod_number, man_id, category_id, dry_run=dry_run)

    if mod_id is None:
        if not mod_number:
            log.warning("Skipping '%s': no model in Intune payload", device_name)
        else:
            log.warning(
                "Skipping '%s': could not resolve model_id for '%s'",
                device_name,
                mod_number,
            )
        return SyncOutcome.SKIPPED_NO_MODEL

    status_id = _resolve_status_id(snipe, device, default_status_id, config)
    existing = snipe.ensure_asset_for_sync(serial, config=config)

    checkout_on_create = (
        config.checkout_on_create
        and checkout_target_id is not None
    )

    if existing:
        asset_id = existing["id"]
        update_payload = _build_asset_payload(
            device,
            device_name=device_name,
            serial=serial,
            man_id=man_id,
            mod_id=mod_id,
            status_id=status_id,
            config=config,
            man_name=man_name,
            mod_number=mod_number,
            checkout_mode=checkout_mode,
            checkout_target_id=None,
            for_create=False,
            autopilot=autopilot,
        )
        if existing.get("archived") in (True, 1, "1"):
            update_payload["archived"] = 0
        if dry_run:
            log.info("[DRY RUN] Would update existing asset %d (%s)", asset_id, device_name)
            if not _apply_checkout_if_needed(
                snipe, asset_id, checkout_mode, checkout_target_id, upn, existing, dry_run=True
            ):
                return SyncOutcome.UPDATED_CHECKOUT_FAILED
            return SyncOutcome.DRY_RUN_UPDATE
        if not snipe.update_asset(asset_id, update_payload):
            return SyncOutcome.UPDATE_FAILED
        log.info("Updated existing asset %d: %s", asset_id, device_name)
        if not _apply_checkout_if_needed(
            snipe, asset_id, checkout_mode, checkout_target_id, upn, existing, dry_run=False
        ):
            return SyncOutcome.UPDATED_CHECKOUT_FAILED
        return SyncOutcome.UPDATED

    create_payload = _build_asset_payload(
        device,
        device_name=device_name,
        serial=serial,
        man_id=man_id,
        mod_id=mod_id,
        status_id=status_id,
        config=config,
        man_name=man_name,
        mod_number=mod_number,
        checkout_mode=checkout_mode,
        checkout_target_id=checkout_target_id if checkout_on_create else None,
        for_create=True,
        autopilot=autopilot,
    )

    if dry_run:
        checkout_hint = upn or "none"
        if checkout_mode == "location":
            checkout_hint = _upn_location_prefix(upn, config.location_prefix_len) or checkout_hint
        log.info(
            "[DRY RUN] Would create asset: %s (serial: %s, checkout %s: %s)",
            device_name,
            serial,
            checkout_mode,
            checkout_hint,
        )
        return SyncOutcome.DRY_RUN_CREATE

    asset = snipe.create_asset(create_payload)
    if not asset:
        return SyncOutcome.CREATE_FAILED
    asset_id = asset["id"]
    log.info("Created asset %d: %s", asset_id, device_name)

    if checkout_target_id and not checkout_on_create:
        if not _apply_checkout_if_needed(
            snipe, asset_id, checkout_mode, checkout_target_id, upn, None, dry_run=False
        ):
            return SyncOutcome.CREATED_CHECKOUT_FAILED
    return SyncOutcome.CREATED


def _format_summary(counts: dict[SyncOutcome, int], dry_run: bool) -> str:
    parts = []
    for key, label in (
        (SyncOutcome.CREATED, "created"),
        (SyncOutcome.UPDATED, "updated"),
        (SyncOutcome.CREATE_FAILED, "create failed"),
        (SyncOutcome.UPDATE_FAILED, "update failed"),
        (SyncOutcome.CREATED_CHECKOUT_FAILED, "created (checkout failed)"),
        (SyncOutcome.UPDATED_CHECKOUT_FAILED, "updated (checkout failed)"),
        (SyncOutcome.CHECKED_IN_STALE, "checked in (stale)"),
        (SyncOutcome.LIFECYCLE_PENDING_RETIRE, "lifecycle pending retire"),
        (SyncOutcome.LIFECYCLE_PENDING_AUTOPILOT, "lifecycle pending autopilot"),
        (SyncOutcome.LIFECYCLE_ARCHIVED, "lifecycle archived"),
        (SyncOutcome.LIFECYCLE_FAILED, "lifecycle failed"),
        (SyncOutcome.SKIPPED_NO_SERIAL, "skipped (no serial)"),
        (SyncOutcome.SKIPPED_NO_MODEL, "skipped (no model)"),
        (SyncOutcome.SKIPPED_STALE, "skipped (stale)"),
        (SyncOutcome.DRY_RUN_CREATE, "would create"),
        (SyncOutcome.DRY_RUN_UPDATE, "would update"),
        (SyncOutcome.DRY_RUN_LIFECYCLE, "would lifecycle update"),
    ):
        n = counts.get(key, 0)
        if n:
            parts.append(f"{n} {label}")
    prefix = "[DRY RUN] " if dry_run else ""
    return prefix + "Summary: " + (", ".join(parts) if parts else "no actions")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Intune managed devices to Snipe-IT")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print actions without writing to Snipe-IT")
    parser.add_argument("--platform", choices=["windows", "android", "ios", "macos", "all"],
                        default="all", help="Filter devices by OS (default: all)")
    parser.add_argument("--groups", type=str, default=None,
                        help="Comma-separated Azure AD group IDs to filter by. "
                             "Falls back to AZURE_GROUP_IDS env var.")
    parser.add_argument(
        "--use-primary-user",
        action="store_true",
        help="Resolve assignee from Graph primary user (beta /users); "
             "overrides GRAPH_USE_PRIMARY_USER when set",
    )
    args = parser.parse_args()

    group_ids: list[str] | None = None
    if args.groups:
        group_ids = [gid.strip() for gid in args.groups.split(",") if gid.strip()]
    else:
        group_ids = _parse_group_ids(os.getenv("AZURE_GROUP_IDS"))

    use_primary = True if args.use_primary_user else None
    config = SyncConfig.from_env(use_primary_user_cli=use_primary)

    graph = GraphClient()
    snipe = SnipeITClient(config)

    autopilot_by_serial: dict[str, dict] = {}
    if _platform_includes_windows(args.platform) and not config.skip_autopilot:
        autopilot_by_serial = graph.fetch_autopilot_by_serial()

    devices = fetch_managed_devices(graph, args.platform, group_ids=group_ids)
    filter_info = f"platform '{args.platform}'"
    if group_ids:
        filter_info += f" and {len(group_ids)} group(s)"
    log.info("Found %d Intune devices matching %s", len(devices), filter_info)

    primary_upns: dict[str, str] = {}
    if config.use_primary_user:
        device_ids = [d["id"] for d in devices if d.get("id")]
        primary_upns = graph.fetch_primary_user_upns(device_ids)

    category_id = snipe.get_or_create_category("Intune", dry_run=args.dry_run)
    default_status_id = _resolve_startup_status_id(
        snipe,
        config.default_status_name,
        auto_create=config.auto_create_default_status,
        dry_run=args.dry_run,
    )
    if _status_unavailable(
        default_status_id,
        auto_create=config.auto_create_default_status,
        dry_run=args.dry_run,
    ):
        log.error(
            "Cannot proceed without status label '%s' "
            "(create it in Snipe-IT or use the built-in default name)",
            config.default_status_name,
        )
        sys.exit(1)

    if config.checkout_status_name:
        checkout_id = snipe.get_status_id(config.checkout_status_name)
        if checkout_id is None:
            log.error("Checkout status label '%s' not found", config.checkout_status_name)
            sys.exit(1)
        snipe._checkout_status_id = checkout_id
    elif default_status_id is not None:
        snipe._checkout_status_id = default_status_id

    if config.checkin_status_name:
        checkin_id = snipe.get_status_id(config.checkin_status_name)
        if checkin_id is None:
            log.error("Checkin status label '%s' not found", config.checkin_status_name)
            sys.exit(1)
        snipe._checkin_status_id = checkin_id
    elif default_status_id is not None:
        snipe._checkin_status_id = default_status_id

    lifecycle_status_ids: dict[str, int | None] = {
        "pending_retire": _resolve_startup_status_id(
            snipe,
            config.status_pending_retire,
            auto_create=config.auto_create_pending_retire,
            dry_run=args.dry_run,
        ),
    }
    if _status_unavailable(
        lifecycle_status_ids["pending_retire"],
        auto_create=config.auto_create_pending_retire,
        dry_run=args.dry_run,
    ):
        log.warning(
            "Lifecycle status label '%s' not found; retiring devices use default status",
            config.status_pending_retire,
        )
    if config.lifecycle_reconciliation and config.sync_state_file:
        lifecycle_status_ids["pending_autopilot"] = _resolve_startup_status_id(
            snipe,
            config.status_pending_autopilot,
            auto_create=config.auto_create_pending_autopilot,
            dry_run=args.dry_run,
        )
        lifecycle_status_ids["archived"] = _resolve_startup_status_id(
            snipe,
            config.status_archived,
            auto_create=config.auto_create_archived,
            dry_run=args.dry_run,
        )
        for label, sid, auto_create in (
            (
                config.status_pending_autopilot,
                lifecycle_status_ids["pending_autopilot"],
                config.auto_create_pending_autopilot,
            ),
            (
                config.status_archived,
                lifecycle_status_ids["archived"],
                config.auto_create_archived,
            ),
        ):
            if _status_unavailable(sid, auto_create=auto_create, dry_run=args.dry_run):
                log.error(
                    "Lifecycle status label '%s' not found in Snipe-IT "
                    "(required when SYNC_STATE_FILE is set)",
                    label,
                )
                sys.exit(1)

    log.info(
        "Using category_id=%s, default_status_id=%s, checkout_mode=%s, "
        "primary_user=%s, custom_fields=%d, autopilot=%d, lifecycle_reconcile=%s",
        category_id,
        default_status_id,
        config.checkout_mode,
        config.use_primary_user,
        len(config.custom_fields),
        len(autopilot_by_serial),
        config.lifecycle_reconciliation and bool(config.sync_state_file),
    )

    previous_state = load_sync_state(config.sync_state_file)
    sync_state: dict[str, Any] = {}
    current_intune_serials: set[str] = set()
    counts: dict[SyncOutcome, int] = {o: 0 for o in SyncOutcome}
    for dev in devices:
        ap_record: dict | None = None
        if _is_windows_device(dev) and autopilot_by_serial:
            serial_key = (dev.get("serialNumber") or "").casefold()
            ap_record = autopilot_by_serial.get(serial_key)
            _enrich_device_autopilot(dev, ap_record)

        outcome = sync_device(
            snipe,
            dev,
            category_id=category_id,
            default_status_id=default_status_id,
            config=config,
            dry_run=args.dry_run,
            primary_upns=primary_upns,
            autopilot=ap_record,
            status_ids=lifecycle_status_ids,
        )
        counts[outcome] += 1
        serial = dev.get("serialNumber")
        if serial and config.sync_state_file:
            current_intune_serials.add(serial)
            sync_state[serial] = {
                "intune_id": dev.get("id"),
                "device_name": dev.get("deviceName"),
                "platform": _device_platform_key(dev),
                "manufacturer": dev.get("manufacturer"),
                "model": dev.get("model"),
                "last_sync": dev.get("lastSyncDateTime"),
                "management_state": dev.get("managementState"),
                "outcome": outcome.value,
                "synced_at": datetime.now(tz=timezone.utc).isoformat(),
            }

    if config.sync_state_file and config.lifecycle_reconciliation:
        recon_counts = reconcile_missing_devices(
            snipe,
            config,
            previous_state,
            current_intune_serials,
            autopilot_by_serial,
            platform=args.platform,
            default_status_id=default_status_id,
            status_ids=lifecycle_status_ids,
            dry_run=args.dry_run,
        )
        for outcome, n in recon_counts.items():
            counts[outcome] += n

    save_sync_state(config.sync_state_file, sync_state)
    log.info("%s", _format_summary(counts, args.dry_run))


if __name__ == "__main__":
    main()
