#!/usr/bin/env python3
import os
import re
import sys
import json
import argparse
import requests
from msal import ConfidentialClientApplication

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TENANT_ID             = os.getenv("AZURE_TENANT_ID",     "your-tenant-id")
CLIENT_ID             = os.getenv("AZURE_CLIENT_ID",     "your-client-id")
CLIENT_SECRET         = os.getenv("AZURE_CLIENT_SECRET", "your-client-secret")
AUTHORITY             = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE                 = ["https://graph.microsoft.com/.default"]

# Snipe-IT base URL must end in "/api/v1"
SNIPEIT_URL           = os.getenv("SNIPEIT_URL",       "https://your-snipeit-url/api/v1")
SNIPEIT_API_TOKEN     = os.getenv("SNIPEIT_API_TOKEN", "your-snipeit-api-token")
# Default asset status label name (must match an existing Snipe-IT status label)
DEFAULT_STATUS_NAME   = os.getenv("SNIPEIT_DEFAULT_STATUS", "Ready to Deploy")
# Azure AD Group IDs to filter devices (comma-separated list of group object IDs)
# Only devices that are members of these groups will be synced
AZURE_GROUP_IDS       = os.getenv("AZURE_GROUP_IDS", "").split(",") if os.getenv("AZURE_GROUP_IDS") else []
AZURE_GROUP_IDS       = [gid.strip() for gid in AZURE_GROUP_IDS if gid.strip()]
# ────────────────────────────────────────────────────────────────────────────────

# MSAL client setup for Graph API
auth_app = ConfidentialClientApplication(
    client_id=CLIENT_ID,
    client_credential=CLIENT_SECRET,
    authority=AUTHORITY
)
token = auth_app.acquire_token_for_client(scopes=SCOPE)
if "access_token" not in token:
    raise RuntimeError("Failed to acquire Graph access token")

headers_graph = {"Authorization": f"Bearer {token['access_token']}"}
headers_snipeit = {
    "Authorization": f"Bearer {SNIPEIT_API_TOKEN}",
    "Accept":        "application/json",
    "Content-Type":  "application/json",
}

# Regex to strip Android-Enterprise GUID prefixes from UPNs
GUID_PREFIX = re.compile(r'^[0-9a-f]{32}')

def normalize_upn(upn_raw):
    if not upn_raw:
        return None
    m = GUID_PREFIX.match(upn_raw)
    return upn_raw[m.end():] if m else upn_raw

# ─── SNIPE-IT LOOKUPS & CREATORS ─────────────────────────────────────────────

def get_or_create_category(name):
    if not name:
        return None
    r = requests.get(f"{SNIPEIT_URL}/categories?search={name}", headers=headers_snipeit)
    r.raise_for_status()
    rows = r.json().get("rows", [])
    if rows:
        return rows[0]["id"]
    payload = {"name": name, "category_type": "asset"}
    c = requests.post(f"{SNIPEIT_URL}/categories", headers=headers_snipeit, json=payload)
    if c.status_code in (200, 201) and c.json().get("payload"):
        return c.json()["payload"]["id"]
    print(f"[WARN] Could not create category '{name}': {c.status_code} {c.text}")
    return None


def get_or_create_manufacturer(name):
    if not name:
        return None
    r = requests.get(f"{SNIPEIT_URL}/manufacturers?search={name}", headers=headers_snipeit)
    r.raise_for_status()
    rows = r.json().get("rows", [])
    if rows:
        return rows[0]["id"]
    payload = {"name": name}
    c = requests.post(f"{SNIPEIT_URL}/manufacturers", headers=headers_snipeit, json=payload)
    if c.status_code in (200, 201) and c.json().get("payload"):
        return c.json()["payload"]["id"]
    print(f"[WARN] Could not create manufacturer '{name}': {c.status_code} {c.text}")
    return None


def get_or_create_model(model_number, manufacturer_id, category_id):
    if not model_number:
        return None
    r = requests.get(f"{SNIPEIT_URL}/models?search={model_number}", headers=headers_snipeit)
    r.raise_for_status()
    rows = r.json().get("rows", [])
    for row in rows:
        if row.get("model_number") == model_number or row.get("name") == model_number:
            return row["id"]
    payload = {
        "name":            model_number,
        "model_number":    model_number,
        "manufacturer_id": manufacturer_id,
        "category_id":     category_id
    }
    c = requests.post(f"{SNIPEIT_URL}/models", headers=headers_snipeit, json=payload)
    if c.status_code in (200, 201) and c.json().get("payload"):
        return c.json()["payload"]["id"]
    print(f"[WARN] Could not create model '{model_number}': {c.status_code} {c.text}")
    return None


def get_status_id(name):
    try:
        r = requests.get(f"{SNIPEIT_URL}/statuslabels", headers=headers_snipeit)
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] Unable to fetch status labels: {e}")
        return None
    rows = r.json().get("rows", [])
    for sl in rows:
        if sl.get("name") == name:
            return sl.get("id")
    print(f"[ERROR] Status label '{name}' not found. Available: {[sl.get('name') for sl in rows]}")
    return None


def get_snipeit_user_id(upn):
    if not upn:
        return None
    r = requests.get(f"{SNIPEIT_URL}/users?search={upn}", headers=headers_snipeit)
    r.raise_for_status()
    rows = r.json().get("rows", [])
    return rows[0]["id"] if rows else None
# ────────────────────────────────────────────────────────────────────────────────


def fetch_azure_ad_device_ids_from_groups(group_ids):
    """
    Fetch Azure AD device IDs from the specified groups.
    Returns a set of Azure AD device object IDs.
    """
    if not group_ids:
        return None  # None means no filtering
    
    device_ids = set()
    for group_id in group_ids:
        if not group_id:
            continue
        url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/microsoft.graph.device"
        while url:
            try:
                r = requests.get(url, headers=headers_graph)
                if r.status_code == 404:
                    print(f"[WARN] Group {group_id} not found or not accessible")
                    break
                if r.status_code == 403:
                    raise RuntimeError(f"403 Forbidden accessing group {group_id}: check Group.Read.All permission")
                r.raise_for_status()
                data = r.json()
                for device in data.get("value", []):
                    device_ids.add(device.get("id"))
                url = data.get("@odata.nextLink")
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Failed to fetch devices from group {group_id}: {e}")
                break
    
    print(f"Found {len(device_ids)} Azure AD devices from {len(group_ids)} group(s)")
    return device_ids


def fetch_managed_devices(platform, group_ids=None):
    """
    Fetch Intune managed devices, optionally filtering by operatingSystem and group membership.
    
    Args:
        platform: OS platform filter ('windows', 'android', 'ios', 'macos', 'all')
        group_ids: List of Azure AD group IDs to filter by. If None or empty, no group filtering is applied.
    
    Returns:
        List of managed devices that match the platform and group filters.
    """
    # Fetch Azure AD device IDs from groups if group filtering is enabled
    azure_ad_device_ids = None
    if group_ids:
        azure_ad_device_ids = fetch_azure_ad_device_ids_from_groups(group_ids)
        if azure_ad_device_ids is not None and len(azure_ad_device_ids) == 0:
            print("[WARN] No devices found in specified groups, no devices will be synced")
            return []
    
    url = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
    devices = []
    while url:
        r = requests.get(url, headers=headers_graph)
        if r.status_code == 403:
            raise RuntimeError("403 Forbidden fetching devices: check permissions")
        r.raise_for_status()
        data = r.json()
        for dev in data.get("value", []):
            # Filter by platform
            os_val = dev.get("operatingSystem", "").lower()
            platform_match = (
                platform == 'all' or
                (platform == 'windows' and os_val.startswith('windows')) or
                (platform == 'android' and 'android' in os_val) or
                (platform == 'ios' and 'ios' in os_val) or
                (platform == 'macos' and 'mac' in os_val)
            )
            
            if not platform_match:
                continue
            
            # Filter by group membership if groups are specified
            if azure_ad_device_ids is not None:
                azure_ad_device_id = dev.get("azureActiveDeviceId") or dev.get("azureADDeviceId")
                if azure_ad_device_id not in azure_ad_device_ids:
                    continue  # Skip devices not in the specified groups
            
            devices.append(dev)
        url = data.get("@odata.nextLink")
    return devices


def send_to_snipeit(device, category_id, status_id, dry_run=False):
    raw_upn = device.get("userPrincipalName")
    upn = normalize_upn(raw_upn)
    snipe_user_id = get_snipeit_user_id(upn)

    man_name = device.get("manufacturer")
    mod_number = device.get("model")
    man_id = get_or_create_manufacturer(man_name)
    mod_id = get_or_create_model(mod_number, man_id, category_id) if man_id else None

    if mod_id is None:
        print(f"[WARN] Skipping '{device.get('deviceName')}': model_id unavailable")
        return

    payload = {
        "name": device.get("deviceName"),
        "serial": device.get("serialNumber"),
        "manufacturer_id": man_id,
        "model_id": mod_id,
        "status_id": status_id,
        "notes": f"Imported from Intune: {man_name} {mod_number}"
    }

    if dry_run:
        print("[DRY RUN]", json.dumps(payload), "→ checkout to user_id", snipe_user_id)
        return

    r = requests.post(f"{SNIPEIT_URL}/hardware", headers=headers_snipeit, json=payload)
    resp = r.json()
    if r.status_code not in (200, 201) or resp.get("status") != "success":
        print(f"[ERROR] Failed to create '{device.get('deviceName')}': {r.status_code} {r.text}")
        return

    asset_id = resp["payload"]["id"]
    print(f"Imported: {device.get('deviceName')} → asset ID {asset_id}")

    if snipe_user_id:
        co = requests.post(
            f"{SNIPEIT_URL}/hardware/{asset_id}/checkout",
            headers=headers_snipeit,
            json={"user_id": snipe_user_id}
        )
        if co.status_code in (200, 201) and co.json().get("status") == "success":
            print(f"Checked out asset {asset_id} to user_id {snipe_user_id}")
        else:
            print(f"[ERROR] Checkout failed for asset {asset_id}: {co.status_code} {co.text}")


def main(dry_run, platform, group_ids=None):
    devices = fetch_managed_devices(platform, group_ids=group_ids)
    filter_info = f"platform '{platform}'"
    if group_ids:
        filter_info += f" and {len(group_ids)} group(s)"
    print(f"Found {len(devices)} Intune devices matching {filter_info}")
    category_id = get_or_create_category("Intune")
    status_id = get_status_id(DEFAULT_STATUS_NAME)
    if status_id is None:
        sys.exit(1)
    print(f"Using category_id={category_id}, status_id={status_id}")
    for d in devices:
        send_to_snipeit(d, category_id=category_id, status_id=status_id, dry_run=dry_run)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Intune → Snipe-IT")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing to Snipe-IT")
    parser.add_argument(
        "--platform", choices=["windows", "android", "ios", "macos", "all"],
        default="all", help="Filter devices by OS"
    )
    parser.add_argument(
        "--groups", type=str, default=None,
        help="Comma-separated list of Azure AD group object IDs to filter devices by membership. "
             "Alternatively, use AZURE_GROUP_IDS environment variable."
    )
    args = parser.parse_args()
    
    # Use --groups argument if provided, otherwise fall back to environment variable
    group_ids = None
    if args.groups:
        group_ids = [gid.strip() for gid in args.groups.split(",") if gid.strip()]
    elif AZURE_GROUP_IDS:
        group_ids = AZURE_GROUP_IDS
    
    main(dry_run=args.dry_run, platform=args.platform, group_ids=group_ids)
