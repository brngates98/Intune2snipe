# Configuration

## Required environment variables

| Variable | Purpose |
|----------|---------|
| `AZURE_TENANT_ID` | Azure AD tenant directory ID (GUID) |
| `AZURE_CLIENT_ID` | Application (client) ID of the app registration |
| `AZURE_CLIENT_SECRET` | Client secret value |
| `SNIPEIT_URL` | Snipe-IT base API URL — **must end with** `/api/v1` |
| `SNIPEIT_API_TOKEN` | Snipe-IT personal API token |
| `SNIPEIT_DEFAULT_STATUS` | Default Snipe-IT status label name (default: `Ready to Deploy`; **auto-created** if missing when unset) |

## Optional — sync behavior

| Variable | Purpose |
|----------|---------|
| `AZURE_GROUP_IDS` | Comma-separated Azure AD **group object IDs** (see [Usage & CLI](usage-and-cli.md)) |
| `SNIPEIT_CHECKOUT_MODE` | Checkout target: `user` (default) or `location` |
| `SNIPEIT_LOCATION_PREFIX_LENGTH` | UPN prefix length for location checkout (default: `3`) |
| `SNIPEIT_CHECKOUT_STATUS` | Status label applied on checkout (default: `SNIPEIT_DEFAULT_STATUS`) |
| `SNIPEIT_CHECKIN_STATUS` | Status label applied on checkin (default: `SNIPEIT_DEFAULT_STATUS`) |
| `SNIPEIT_SKIP_CHECKOUT_ON_CREATE` | Set to `true` to omit assignee on create (always checkout in a second call) |
| `GRAPH_USE_PRIMARY_USER` | Set to `true` to resolve assignee from Graph **primary user** (`/beta/.../users`) instead of enrolled UPN |
| `SNIPEIT_COMPANY_ID` | Snipe-IT company id for multi-company installs |
| `SNIPEIT_STALE_DAYS` | If set, devices not synced to Intune within this many days are checked in (when an asset exists) |
| `SYNC_STATE_FILE` | Path to write JSON sync state after each run; **required for lifecycle reconciliation** (serials absent from Intune → archived / pending Autopilot) |
| `SNIPEIT_INCLUDE_DELETED_ASSETS` | Set to `true` to match soft-deleted Snipe assets via `byserial?deleted=true` |
| `SNIPEIT_SKIP_RESTORE_DELETED` | Set to `true` to skip `POST /hardware/{id}/restore` when a soft-deleted asset is found (default: restore before sync) |
| `SNIPEIT_SKIP_LIFECYCLE_RECONCILIATION` | Set to `true` to skip the post-sync pass that archives devices missing from Intune |
| `SNIPEIT_SKIP_AUTOPILOT` | Set to `true` to skip Windows Autopilot lookup (default: **automatic** when syncing `windows` or `all`) |
| `SNIPEIT_STATUS_PENDING_AUTOPILOT` | Snipe status when Windows device left Intune but remains in Autopilot pending re-deploy (default: `Pending Autopilot`) |
| `SNIPEIT_STATUS_PENDING_RETIRE` | Snipe status when Intune `managementState` is retire/wipe/delete in progress (default: `Pending Retire`) |
| `SNIPEIT_STATUS_ARCHIVED` | Snipe status when device left Intune and is not Autopilot-pending (default: `Archived`) |
| `SNIPEIT_SKIP_STATUS_AUTO_CREATE` | Set to `true` to never create missing status labels via API (default: auto-create built-in default names only) |

CLI: `--use-primary-user` enables primary-user lookup for a single run (overrides `GRAPH_USE_PRIMARY_USER` when passed).

## Optional — custom fields & compliance

Map Intune properties to Snipe-IT **custom field DB column names** (from **Settings → Custom Fields**):

| Variable | Intune field |
|----------|----------------|
| `SNIPEIT_CF_INTUNE_DEVICE_ID` | `id` |
| `SNIPEIT_CF_AZURE_AD_DEVICE_ID` | `azureADDeviceId` |
| `SNIPEIT_CF_OS_VERSION` | `osVersion` |
| `SNIPEIT_CF_LAST_INTUNE_SYNC` | `lastSyncDateTime` |
| `SNIPEIT_CF_IMEI` | `imei` |
| `SNIPEIT_CF_MEID` | `meid` |
| `SNIPEIT_CF_WIFI_MAC` | `wiFiMacAddress` |
| `SNIPEIT_CF_COMPLIANCE_STATE` | `complianceState` |
| `SNIPEIT_CF_AUTOPILOT_ENROLLMENT_STATE` | Autopilot `enrollmentState` (Windows) |
| `SNIPEIT_CF_AUTOPILOT_LAST_CONTACTED` | Autopilot `lastContactedDateTime` (Windows) |

Additional mappings: `SNIPEIT_CUSTOM_FIELDS` JSON object, e.g.:

```bash
export SNIPEIT_CUSTOM_FIELDS='{"id":"intune_device_id","osVersion":"os_version"}'
```

Compliance → status label map:

```bash
export SNIPEIT_COMPLIANCE_STATUS_MAP='{"compliant":"Ready to Deploy","noncompliant":"Out for Repair"}'
```

## Example shell exports

```bash
export AZURE_TENANT_ID="<your-tenant-guid>"
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"

export SNIPEIT_URL="https://my-snipeit.example.com/api/v1"
export SNIPEIT_API_TOKEN="<your-snipeit-api-token>"
export SNIPEIT_DEFAULT_STATUS="Ready to Deploy"
export SNIPEIT_CHECKOUT_STATUS="Deployed"

# Optional group filter
export AZURE_GROUP_IDS="<group-id-1>,<group-id-2>"

# Optional: primary user + custom fields
export GRAPH_USE_PRIMARY_USER=true
export SNIPEIT_CF_INTUNE_DEVICE_ID=intune_device_id
export SNIPEIT_CF_OS_VERSION=os_version

# Lifecycle + Windows Autopilot (recommended for production Windows sync)
export SYNC_STATE_FILE=/var/lib/intune2snipe/sync-state.json
export SNIPEIT_STATUS_PENDING_AUTOPILOT="Pending Autopilot"
export SNIPEIT_STATUS_PENDING_RETIRE="Pending Retire"
export SNIPEIT_STATUS_ARCHIVED="Archived"
# Optional Autopilot custom fields (Windows only)
export SNIPEIT_CF_AUTOPILOT_ENROLLMENT_STATE=autopilot_enrollment_state
export SNIPEIT_CF_AUTOPILOT_LAST_CONTACTED=autopilot_last_contacted
```

## Azure AD app registration

1. Open [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations**  
2. Create an app or pick an existing one  
3. **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions**  
4. Add at least:
   - `DeviceManagementManagedDevices.Read.All` — [List managedDevices](https://learn.microsoft.com/en-us/graph/api/intune-devices-manageddevice-list)  
   - `DeviceManagementServiceConfig.Read.All` — [List windowsAutopilotDeviceIdentities](https://learn.microsoft.com/en-us/graph/api/intune-enrollment-windowsautopilotdeviceidentity-list) (automatic for Windows sync)  
   - `User.Read.All` — user lookup for checkout and primary-user resolution  
   - If you use **group filtering**: `GroupMember.Read.All` or `Group.Read.All` — [List group members](https://learn.microsoft.com/en-us/graph/api/group-list-members)  
5. Click **Grant admin consent** for your tenant  
6. **Certificates & secrets** → create a **client secret** and copy the **value** (not only the ID)  

## Snipe-IT API token

1. Sign in to Snipe-IT  
2. **My Account** → **API Tokens**  
3. Create a token with permissions appropriate for creating/updating assets and checkout  
4. Store it securely; you may not be able to view it again  

### Lifecycle status labels (when using `SYNC_STATE_FILE`)

When you use the **built-in default names** (leave `SNIPEIT_DEFAULT_STATUS` and `SNIPEIT_STATUS_*` unset, or set them to the defaults below), intune2snipe **creates any missing status labels** in Snipe-IT via `POST /statuslabels` on startup:

- **Ready to Deploy** (`deployable`) — default status for new/updated assets  
- **Pending Autopilot** (`pending`) — Windows device gone from Intune, still in Autopilot awaiting re-deploy  
- **Pending Retire** (`pending`) — Intune retire/wipe/delete in progress  
- **Archived** (`archived`) — Device removed from Intune and not Autopilot-pending  

If you set a **custom** name via `SNIPEIT_DEFAULT_STATUS` or `SNIPEIT_STATUS_*`, that label must **already exist** in Snipe-IT (same as checkout/checkin overrides). Set `SNIPEIT_SKIP_STATUS_AUTO_CREATE=true` to disable all auto-creation.

Compliance-driven statuses from `SNIPEIT_COMPLIANCE_STATUS_MAP` must always exist in Snipe-IT; they are never auto-created.

## Security notes

- Do not commit secrets to git  
- Treat the client secret and API token like passwords  
- In Kubernetes, use **Secrets** (or Sealed Secrets / External Secrets / SOPS); see [Deployment — Kubernetes](deployment-kubernetes.md)  
