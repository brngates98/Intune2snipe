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
- Snipe-IT REST API — Users index (email / username query params):
  https://snipe-it.readme.io/reference/users

Usage:
    python3 app.py --dry-run --platform windows
    python3 app.py --dry-run --groups "group-id-1,group-id-2"
    python3 app.py --platform all
    python3 app.py --limit 10
    python3 app.py --secret-store aws-secrets-manager --secret-name my/secret

Dependencies: requests, msal, azure-identity (certificate auth), python-dotenv (optional .env).
Secret backends (AWS, Vault, Azure Key Vault) need optional packages — see docs/configuration.md.
"""
from __future__ import annotations

import argparse
import ipaddress
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse

import requests
from msal import ConfidentialClientApplication
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from secret_stores import (
    apply_secrets_to_env,
    load_from_aws_secrets_manager,
    load_from_azure_keyvault,
    load_from_vault,
)

# ─── LOGGING ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("intune2snipe")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

# (connect timeout, read timeout) — aligns with common production client defaults
DEFAULT_TIMEOUT = (3.05, 30)

# Refresh the Graph token this many seconds before MSAL expiry to avoid
# mid-pagination failures on long syncs (see MSAL token response `expires_in`).
GRAPH_TOKEN_SKEW_SECONDS = 300

# Regex to strip Android-Enterprise GUID prefixes from UPNs
GUID_PREFIX = re.compile(r"^[0-9a-f]{32}")

# Azure AD object IDs (group IDs) are UUIDs — reject malformed values early
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_placeholder(value: str | None) -> bool:
    """Treat empty or README-style ``your-...`` values as unset."""
    if not value or not str(value).strip():
        return True
    return str(value).strip().lower().startswith("your-")


def _assemble_cert_pem() -> str | None:
    """Build PEM bytes source from combined or split certificate env vars."""
    combined = os.getenv("AZURE_COMBINED_CERT_KEY")
    if combined and not _is_placeholder(combined):
        return combined.strip()
    cert = os.getenv("AZURE_CERTIFICATE_PEM")
    key = os.getenv("AZURE_PRIVATE_KEY_PEM")
    if cert and key and not _is_placeholder(cert) and not _is_placeholder(key):
        return f"{cert.strip()}\n{key.strip()}"
    return None


def normalize_snipe_url(url: str) -> str:
    """Ensure ``SNIPEIT_URL`` ends with ``/api/v1`` when a base URL is given."""
    u = (url or "").strip()
    if not u:
        return u
    u = u.rstrip("/")
    if u.endswith("/api/v1"):
        return u
    if u.endswith("/api"):
        u = u + "/v1"
    elif not u.endswith("/api/v1"):
        u = u + "/api/v1"
    log.warning("SNIPEIT_URL normalized to: %s", u)
    return u


def validate_snipe_url(url: str) -> None:
    """Require HTTPS and a hostname; block literal private IPs unless opted in."""
    if not url:
        raise ValueError("SNIPEIT_URL is empty.")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"SNIPEIT_URL must use HTTPS (got scheme {parsed.scheme!r}).")
    if not parsed.hostname:
        raise ValueError("SNIPEIT_URL has no valid hostname.")
    allow_private = os.getenv("SNIPEIT_ALLOW_PRIVATE_IP", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return  # hostname is not an IP literal
    if not allow_private and (ip.is_private or ip.is_loopback or ip.is_link_local):
        raise ValueError(
            "SNIPEIT_URL must not point to a private, loopback, or link-local IP "
            "unless SNIPEIT_ALLOW_PRIVATE_IP is set."
        )


def _http_session() -> requests.Session:
    """Session with retries for transient errors (429 / 5xx).

    Honors ``Retry-After`` when the server sends it. Safe for Snipe-IT
    equality-filtered GETs; POST/PATCH may still duplicate on rare double-submit
    if the first request succeeded but the client timed out—monitor logs.
    """
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


# ─── CLIENTS ──────────────────────────────────────────────────────────────────


class GraphClient:
    """Microsoft Graph API client using certificate or client-secret credentials."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float | None = None
        self._tenant_id = os.getenv("AZURE_TENANT_ID", "").strip()
        self._client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
        self._client_secret = os.getenv("AZURE_CLIENT_SECRET", "").strip()
        self._cert_pem = _assemble_cert_pem()
        self._has_valid_cert = bool(self._cert_pem) and not _is_placeholder(self._cert_pem)
        self._has_valid_secret = bool(self._client_secret) and not _is_placeholder(
            self._client_secret
        )
        self._cert_credential: Any = None
        self._cert_disabled = False
        self._app: ConfidentialClientApplication | None = None
        self._session = _http_session()

        if not self._tenant_id or _is_placeholder(self._tenant_id):
            raise RuntimeError(
                "Azure tenant not configured. Set AZURE_TENANT_ID to your directory ID."
            )
        if not self._client_id or _is_placeholder(self._client_id):
            raise RuntimeError(
                "Azure application not configured. Set AZURE_CLIENT_ID to the app registration client ID."
            )
        if not self._has_valid_cert and not self._has_valid_secret:
            raise RuntimeError(
                "Azure authentication not configured. Set either certificate variables "
                "(AZURE_COMBINED_CERT_KEY, or AZURE_CERTIFICATE_PEM plus AZURE_PRIVATE_KEY_PEM) "
                "or AZURE_CLIENT_SECRET."
            )

    def _get_cert_credential(self) -> Any:
        if self._cert_credential is None:
            from azure.identity import CertificateCredential

            pem = (self._cert_pem or "").encode("utf-8")
            self._cert_credential = CertificateCredential(
                tenant_id=self._tenant_id,
                client_id=self._client_id,
                certificate_data=pem,
            )
        return self._cert_credential

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

        if self._has_valid_cert and not self._cert_disabled:
            try:
                cred = self._get_cert_credential()
                tr = cred.get_token("https://graph.microsoft.com/.default")
                self._token = tr.token
                self._token_expires_at = float(tr.expires_on)
                log.info(
                    "Authenticated with Microsoft Graph (certificate; token expires at %s epoch)",
                    self._token_expires_at,
                )
                return
            except Exception as e:
                log.error("Certificate authentication failed: %s", e)
                if not self._has_valid_secret:
                    raise RuntimeError(
                        "Certificate authentication failed and no AZURE_CLIENT_SECRET is set for fallback."
                    ) from e
                log.warning("Falling back to client secret authentication")
                self._cert_disabled = True

        if self._has_valid_secret:
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
                "Authenticated with Microsoft Graph (client secret; token expires in %s seconds)",
                expires_in,
            )
            return

        raise RuntimeError("No valid Microsoft Graph authentication method available.")

    def _refresh_token(self) -> None:
        self._token = None
        self._token_expires_at = None
        self._ensure_auth()

    def _headers(self) -> dict[str, str]:
        self._ensure_auth()
        assert self._token is not None
        return {"Authorization": f"Bearer {self._token}"}

    def get_paginated(self, url: str) -> list[dict]:
        """Fetch all pages from a Graph API endpoint."""
        results: list[dict] = []
        while url:
            resp = self._session.get(
                url, headers=self._headers(), timeout=DEFAULT_TIMEOUT
            )
            if resp.status_code == 401:
                self._refresh_token()
                resp = self._session.get(
                    url, headers=self._headers(), timeout=DEFAULT_TIMEOUT
                )
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return results


class SnipeITClient:
    """Snipe-IT API client."""

    def __init__(self) -> None:
        raw_url = os.getenv("SNIPEIT_URL", "")
        normalized = normalize_snipe_url(raw_url)
        try:
            validate_snipe_url(normalized)
        except ValueError as e:
            raise RuntimeError(str(e)) from e
        self._base_url = normalized.rstrip("/")
        self._token = os.getenv("SNIPEIT_API_TOKEN", "").strip()
        if not self._base_url or not self._token or _is_placeholder(self._token):
            raise RuntimeError(
                "Snipe-IT credentials not configured. Set SNIPEIT_URL (HTTPS, ending with /api/v1) "
                "and SNIPEIT_API_TOKEN."
            )
        self._session = _http_session()
        # Cache lookups to avoid repeated API calls (keyed by normalized lookup key)
        self._category_cache: dict[str, int] = {}
        self._manufacturer_cache: dict[str, int] = {}
        self._model_cache: dict[str, int] = {}
        self._status_cache: dict[str, int] = {}
        self._user_cache: dict[str, int | None] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._session.get(
            self._url(path),
            headers=self._headers(),
            params=params,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        resp = self._session.post(
            self._url(path),
            headers=self._headers(),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, payload: dict) -> dict:
        resp = self._session.patch(
            self._url(path),
            headers=self._headers(),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Lookups with exact matching ──────────────────────────────────────

    def _find_exact(self, path: str, search: str, match_field: str = "name") -> int | None:
        """Search endpoint and return ID only if there's an exact name match."""
        data = self._get(path, params={"search": search})
        for row in data.get("rows", []):
            if row.get(match_field) == search:
                return row["id"]
        return None

    def get_or_create_category(self, name: str) -> int | None:
        if not name:
            return None
        if name in self._category_cache:
            return self._category_cache[name]
        cat_id = self._find_exact("/categories", name)
        if cat_id:
            self._category_cache[name] = cat_id
            return cat_id
        resp = self._post("/categories", {"name": name, "category_type": "asset"})
        if resp.get("payload"):
            cat_id = resp["payload"]["id"]
            self._category_cache[name] = cat_id
            return cat_id
        log.warning("Could not create category '%s': %s", name, resp)
        return None

    def get_or_create_manufacturer(self, name: str) -> int | None:
        if not name:
            return None
        if name in self._manufacturer_cache:
            return self._manufacturer_cache[name]
        man_id = self._find_exact("/manufacturers", name)
        if man_id:
            self._manufacturer_cache[name] = man_id
            return man_id
        resp = self._post("/manufacturers", {"name": name})
        if resp.get("payload"):
            man_id = resp["payload"]["id"]
            self._manufacturer_cache[name] = man_id
            return man_id
        log.warning("Could not create manufacturer '%s': %s", name, resp)
        return None

    def get_or_create_model(
        self, model_number: str, manufacturer_id: int | None, category_id: int | None
    ) -> int | None:
        if not model_number:
            return None
        if model_number in self._model_cache:
            return self._model_cache[model_number]
        # Check by model_number field for exact match
        data = self._get("/models", params={"search": model_number})
        for row in data.get("rows", []):
            if row.get("model_number") == model_number or row.get("name") == model_number:
                self._model_cache[model_number] = row["id"]
                return row["id"]
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

    def get_status_id(self, name: str) -> int | None:
        if name in self._status_cache:
            return self._status_cache[name]
        data = self._get("/statuslabels")
        for sl in data.get("rows", []):
            if sl.get("name") == name:
                self._status_cache[name] = sl["id"]
                return sl["id"]
        available = [sl.get("name") for sl in data.get("rows", [])]
        log.error("Status label '%s' not found. Available: %s", name, available)
        return None

    def get_user_id(self, upn: str | None) -> int | None:
        """Resolve Snipe-IT user id using equality filters (not fuzzy ``search``).

        Snipe-IT ``GET /users`` supports ``email`` and ``username`` query parameters
        with exact ``WHERE`` matches (see Api\\UsersController ``index``).
        """
        if not upn:
            return None
        cache_key = upn.casefold()
        if cache_key in self._user_cache:
            return self._user_cache[cache_key]

        user_id: int | None = None
        # Prefer email match for UPN-shaped values (typical Azure AD / Snipe email)
        if "@" in upn:
            data = self._get("/users", params={"email": upn})
            for row in data.get("rows", []):
                em = row.get("email")
                if em and em.casefold() == cache_key:
                    user_id = row["id"]
                    break

        if user_id is None:
            data = self._get("/users", params={"username": upn})
            for row in data.get("rows", []):
                if row.get("username") == upn:
                    user_id = row["id"]
                    break

        if user_id is None:
            log.warning(
                "No Snipe-IT user found with matching email or username for %s",
                upn,
            )
        self._user_cache[cache_key] = user_id
        return user_id

    def find_asset_by_serial(self, serial: str) -> dict | None:
        """Look up an existing asset by serial number. Returns asset dict or None."""
        if not serial:
            return None
        data = self._get("/hardware/byserial", params={"serial": serial})
        rows = data.get("rows", [])
        return rows[0] if rows else None

    def create_asset(self, payload: dict) -> dict | None:
        resp = self._post("/hardware", payload)
        if resp.get("status") == "success" and resp.get("payload"):
            return resp["payload"]
        log.error("Failed to create asset: %s", resp)
        return None

    def update_asset(self, asset_id: int, payload: dict) -> bool:
        try:
            data = self._patch(f"/hardware/{asset_id}", payload)
        except requests.RequestException as e:
            log.error("Failed to update asset %d: %s", asset_id, e)
            return False
        if data.get("status") == "success":
            return True
        log.error("Failed to update asset %d: %s", asset_id, data)
        return False

    def checkout_asset(self, asset_id: int, user_id: int) -> bool:
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            resp = self._post(f"/hardware/{asset_id}/checkout", {
                "checkout_to_type": "user",
                "assigned_user": user_id,
                "checkout_at": now,
            })
        except requests.RequestException as e:
            log.error("Checkout failed for asset %d: %s", asset_id, e)
            return False
        if resp.get("status") == "success":
            return True
        log.error("Checkout failed for asset %d: %s", asset_id, resp)
        return False


# ─── SYNC LOGIC ───────────────────────────────────────────────────────────────


def normalize_upn(upn_raw: str | None) -> str | None:
    if not upn_raw:
        return None
    m = GUID_PREFIX.match(upn_raw)
    return upn_raw[m.end():] if m else upn_raw


def fetch_group_device_ids(graph: GraphClient, group_ids: list[str]) -> set[str] | None:
    """Fetch Azure AD device object IDs from specified groups.

    Uses OData cast ``.../members/microsoft.graph.device`` so responses are
    ``device`` resources (``id`` = Azure AD device object id). See Microsoft
    Graph "List group members".
    """
    if not group_ids:
        return None
    device_ids: set[str] = set()
    for group_id in group_ids:
        if not group_id:
            continue
        if not UUID_PATTERN.match(group_id):
            log.warning("Skipping invalid group ID (expected UUID): %s", group_id)
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


def fetch_managed_devices(
    graph: GraphClient, platform: str, group_ids: list[str] | None = None
) -> list[dict]:
    """Fetch Intune managed devices, filtered by platform and optionally group membership.

    Joins Intune ``managedDevice`` records to Azure AD using ``azureADDeviceId``
    (documented on the managedDevice resource). ``azureActiveDeviceId`` is kept as a
    fallback for older payloads.
    """
    azure_ad_device_ids = fetch_group_device_ids(graph, group_ids or [])
    if azure_ad_device_ids is not None and len(azure_ad_device_ids) == 0:
        log.warning("No devices found in specified groups, nothing to sync")
        return []

    url = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
    all_devices = graph.get_paginated(url)

    devices: list[dict] = []
    for dev in all_devices:
        os_val = dev.get("operatingSystem", "").lower()
        platform_match = (
            platform == "all"
            or (platform == "windows" and os_val.startswith("windows"))
            or (platform == "android" and "android" in os_val)
            or (platform == "ios" and "ios" in os_val)
            or (platform == "macos" and "mac" in os_val)
        )
        if not platform_match:
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
    DRY_RUN_UPDATE = "dry_run_update"
    DRY_RUN_CREATE = "dry_run_create"
    UPDATED = "updated"
    UPDATE_FAILED = "update_failed"
    CREATED = "created"
    CREATE_FAILED = "create_failed"
    CREATED_CHECKOUT_FAILED = "created_checkout_failed"


def sync_device(
    snipe: SnipeITClient,
    device: dict,
    category_id: int,
    status_id: int,
    dry_run: bool = False,
) -> SyncOutcome:
    """Sync a single Intune device to Snipe-IT. Creates or updates as needed."""
    device_name = device.get("deviceName", "unknown")
    serial = device.get("serialNumber")
    if not serial:
        log.warning("Skipping '%s': no serial number", device_name)
        return SyncOutcome.SKIPPED_NO_SERIAL

    upn = normalize_upn(device.get("userPrincipalName"))
    snipe_user_id = snipe.get_user_id(upn)

    man_name = device.get("manufacturer")
    mod_number = device.get("model")
    man_id = snipe.get_or_create_manufacturer(man_name)
    mod_id = snipe.get_or_create_model(mod_number, man_id, category_id) if man_id else None

    if mod_id is None:
        log.warning("Skipping '%s': could not resolve model_id", device_name)
        return SyncOutcome.SKIPPED_NO_MODEL

    existing = snipe.find_asset_by_serial(serial)

    if existing:
        asset_id = existing["id"]
        if dry_run:
            log.info("[DRY RUN] Would update existing asset %d (%s)", asset_id, device_name)
            return SyncOutcome.DRY_RUN_UPDATE
        updated = snipe.update_asset(asset_id, {
            "name": device_name,
            "model_id": mod_id,
            "notes": f"Updated from Intune: {man_name} {mod_number}",
        })
        if updated:
            log.info("Updated existing asset %d: %s", asset_id, device_name)
            return SyncOutcome.UPDATED
        return SyncOutcome.UPDATE_FAILED

    payload = {
        "name": device_name,
        "serial": serial,
        "manufacturer_id": man_id,
        "model_id": mod_id,
        "status_id": status_id,
        "notes": f"Imported from Intune: {man_name} {mod_number}",
    }

    if dry_run:
        log.info(
            "[DRY RUN] Would create asset: %s (serial: %s, user: %s)",
            device_name,
            serial,
            upn or "none",
        )
        return SyncOutcome.DRY_RUN_CREATE

    asset = snipe.create_asset(payload)
    if not asset:
        return SyncOutcome.CREATE_FAILED
    asset_id = asset["id"]
    log.info("Created asset %d: %s", asset_id, device_name)

    if snipe_user_id:
        if snipe.checkout_asset(asset_id, snipe_user_id):
            log.info("Checked out asset %d to user %s", asset_id, upn)
        else:
            return SyncOutcome.CREATED_CHECKOUT_FAILED
    return SyncOutcome.CREATED


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def _format_summary(counts: dict[SyncOutcome, int], dry_run: bool) -> str:
    parts = []
    for key, label in (
        (SyncOutcome.CREATED, "created"),
        (SyncOutcome.UPDATED, "updated"),
        (SyncOutcome.CREATE_FAILED, "create failed"),
        (SyncOutcome.UPDATE_FAILED, "update failed"),
        (SyncOutcome.CREATED_CHECKOUT_FAILED, "created (checkout failed)"),
        (SyncOutcome.SKIPPED_NO_SERIAL, "skipped (no serial)"),
        (SyncOutcome.SKIPPED_NO_MODEL, "skipped (no model)"),
        (SyncOutcome.DRY_RUN_CREATE, "would create"),
        (SyncOutcome.DRY_RUN_UPDATE, "would update"),
    ):
        n = counts.get(key, 0)
        if n:
            parts.append(f"{n} {label}")
    prefix = "[DRY RUN] " if dry_run else ""
    return prefix + "Summary: " + (", ".join(parts) if parts else "no actions")


def _load_secrets_from_cli(args: argparse.Namespace) -> None:
    """Populate process env from an external store before clients read configuration."""
    if not args.secret_store:
        return
    if args.secret_store == "aws-secrets-manager":
        if not args.secret_name:
            log.error("--secret-name is required for AWS Secrets Manager")
            sys.exit(1)
        secrets = load_from_aws_secrets_manager(args.secret_name, args.aws_region)
        apply_secrets_to_env(secrets)
    elif args.secret_store == "vault":
        vault_addr = args.vault_addr or os.getenv("VAULT_ADDR")
        vault_path = args.vault_path or args.secret_name
        if not vault_addr:
            log.error("--vault-addr or VAULT_ADDR is required for HashiCorp Vault")
            sys.exit(1)
        if not vault_path:
            log.error("--vault-path or --secret-name is required for HashiCorp Vault")
            sys.exit(1)
        secrets = load_from_vault(vault_addr, vault_path)
        apply_secrets_to_env(secrets)
    elif args.secret_store == "azure-keyvault":
        keyvault_url = args.keyvault_url or os.getenv("AZURE_KEYVAULT_URL")
        if not keyvault_url:
            log.error("--keyvault-url or AZURE_KEYVAULT_URL is required for Azure Key Vault")
            sys.exit(1)
        secrets = load_from_azure_keyvault(keyvault_url)
        apply_secrets_to_env(secrets)


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
        "--secret-store",
        type=str,
        default=None,
        choices=["aws-secrets-manager", "vault", "azure-keyvault"],
        help="Load secrets from an external store (optional; requires extra Python packages)",
    )
    parser.add_argument(
        "--secret-name",
        type=str,
        default=None,
        help="Secret name or path (AWS: secret id; Vault: path if --vault-path omitted)",
    )
    parser.add_argument(
        "--aws-region",
        type=str,
        default="us-east-1",
        help="AWS region for Secrets Manager (default: us-east-1)",
    )
    parser.add_argument(
        "--vault-addr",
        type=str,
        default=None,
        help="HashiCorp Vault base URL (e.g. https://vault.example.com:8200)",
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=None,
        help="Vault KV path (e.g. secret/data/intune2snipe)",
    )
    parser.add_argument(
        "--keyvault-url",
        type=str,
        default=None,
        help="Azure Key Vault URL (e.g. https://myvault.vault.azure.net/)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N devices after filters (testing / rollout)",
    )
    args = parser.parse_args()

    _load_secrets_from_cli(args)

    group_ids: list[str] | None = None
    if args.groups:
        group_ids = [gid.strip() for gid in args.groups.split(",") if gid.strip()]
    else:
        group_ids = _parse_group_ids(os.getenv("AZURE_GROUP_IDS"))

    graph = GraphClient()
    snipe = SnipeITClient()

    devices = fetch_managed_devices(graph, args.platform, group_ids=group_ids)
    if args.limit is not None and args.limit >= 0:
        devices = devices[: args.limit]
    filter_info = f"platform '{args.platform}'"
    if group_ids:
        filter_info += f" and {len(group_ids)} group(s)"
    if args.limit is not None:
        filter_info += f" (limit {args.limit})"
    log.info("Found %d Intune devices matching %s", len(devices), filter_info)

    category_id = snipe.get_or_create_category("Intune")
    status_id = snipe.get_status_id(
        os.getenv("SNIPEIT_DEFAULT_STATUS", "Ready to Deploy")
    )
    if status_id is None:
        log.error("Cannot proceed without a valid status label")
        sys.exit(1)

    log.info("Using category_id=%s, status_id=%s", category_id, status_id)

    counts: dict[SyncOutcome, int] = {o: 0 for o in SyncOutcome}
    for dev in devices:
        outcome = sync_device(
            snipe, dev, category_id=category_id, status_id=status_id, dry_run=args.dry_run
        )
        counts[outcome] += 1

    log.info("%s", _format_summary(counts, args.dry_run))


if __name__ == "__main__":
    main()
