# Troubleshooting

## Authentication (Microsoft Graph)

**403 when fetching devices**

- Confirm `DeviceManagementManagedDevices.Read.All` and **admin consent**  
- Confirm the client secret has **not expired**  

**403 when reading groups**

- Add `GroupMember.Read.All` or `Group.Read.All` and grant consent — [List group members](https://learn.microsoft.com/en-us/graph/api/group-list-members)  
- Verify group **object IDs** are correct  

**403 or warning when fetching Autopilot (Windows)**

- Add `DeviceManagementServiceConfig.Read.All` and grant consent — [List windowsAutopilotDeviceIdentities](https://learn.microsoft.com/en-us/graph/api/intune-enrollment-windowsautopilotdeviceidentity-list)  
- Autopilot lookup runs **automatically** when `--platform` is `windows` or `all` (unless `SNIPEIT_SKIP_AUTOPILOT=true`)  
- A 403 logs a warning and lifecycle falls back to Intune-only (no Pending Autopilot detection)

**Token / login errors**

- Check `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`  
- Regenerate the client secret if unsure  

## Device sync

**No devices**

- Confirm devices are Intune-managed and match `--platform`  
- With group filtering: devices must be **Azure AD registered/joined**  

**No devices in groups**

- Verify group membership in Azure Portal or Graph Explorer  
- Confirm you used **object IDs**, not display names  

**Group filter seems ignored**

- See [How it works](how-it-works.md) — matching uses `azureADDeviceId`  

## Snipe-IT

**Status label not found**

- `SNIPEIT_DEFAULT_STATUS` must **exactly** match an existing label (case-sensitive) under **Settings → Status Labels**  
- With **`SYNC_STATE_FILE`**, also create **Pending Autopilot**, **Pending Retire**, and **Archived** (or match your `SNIPEIT_STATUS_*` overrides) — see [Configuration](configuration.md)  

**Lifecycle / Pending Autopilot not updating**

- **`SYNC_STATE_FILE` must be set and persist between runs** (same path every cron execution; use a volume in Docker/K8s)  
- Reconciliation only runs for serials **seen on the previous run** but missing from Intune **this** run — the first run only builds state; test with two consecutive syncs  
- **Pending Autopilot** applies only to **Windows** serials still in Autopilot with `pendingReset`, `notContacted`, `failed`, or `blocked` enrollment state  
- If Autopilot permission is missing, wiped Windows devices go straight to **Archived** instead of Pending Autopilot  
- Disable reconciliation with `SNIPEIT_SKIP_LIFECYCLE_RECONCILIATION=true`  

**Device stuck in Pending Autopilot after re-enroll**

- When the device reappears in Intune, the next active sync clears `archived` and applies normal compliance/checkout — confirm the serial matches and the device is in the managedDevices list  

**Retire/wipe in Intune but asset still checked out**

- Recent releases check in and set **Pending Retire** when `managementState` is retire/wipe/delete in progress — upgrade to latest `main`  

**Soft-deleted asset not updating**

- The sync restores via `POST /hardware/{id}/restore` before update (unless `SNIPEIT_SKIP_RESTORE_DELETED=true`)  

**Compliance status not changing on existing assets**

- Recent releases apply `SNIPEIT_COMPLIANCE_STATUS_MAP` on **updates** as well as creates — verify the map keys match Intune `complianceState` (case-insensitive)  

**Checkout failed**

- User must exist in Snipe-IT with matching **email** (UPN with `@`) or **username** after normalization  
- Confirm API token can write assets and checkout  

**Checked-out user does not update**

- Recent releases re-checkout on update when the Intune primary user changes  
- When Intune clears the primary user, the sync checks the asset back in  

**Duplicate assets on every run**

- Fixed in recent releases: serial lookup uses `GET /api/v1/hardware/byserial/{serial}`  
- Upgrade to latest `main`/release; existing serials should update instead of creating duplicates  

**`could not resolve model_id` warnings**

- Often caused by manufacturer name casing (`LENOVO` in Intune vs `Lenovo` in Snipe). Recent releases match taxonomy case-insensitively  
- Ensure the model exists in Snipe (by model number or name) or allow the sync to create it on a non-dry-run  

**Location checkout (`SNIPEIT_CHECKOUT_MODE=location`)**

- Set `SNIPEIT_CHECKOUT_MODE=location` and optionally `SNIPEIT_LOCATION_PREFIX_LENGTH` (default `3`)  
- Location names must start with the UPN prefix (e.g. `A55` from `A55@domain.com` → `A55 - somewhere`)  
- Helm: `sync.checkoutMode` / `sync.locationPrefixLength`, or the same keys in your Kubernetes Secret  
- If no matching location exists, checkout is skipped and a warning is logged  

**API / URL errors**

- `SNIPEIT_URL` must end with **`/api/v1`**  
- Test connectivity and token from the same network as the runner  

## Docker / Kubernetes

**Image pull errors**

- For private GHCR: `docker login ghcr.io` or Kubernetes `imagePullSecret`  
- Confirm tag exists (`latest`, `v1.0.0`, etc.)  

**Container exits or CronJob never succeeds**

- Inspect logs: `docker logs …` or `kubectl logs …`  
- Verify **all** required env vars are present in the Secret  

**CronJob not on schedule**

- `kubectl describe cronjob …` — check schedule, suspend, last schedule time  
- Check job history: `kubectl get jobs -l app=…`  

## Debugging checklist

1. Run with **`--dry-run`** first  
2. Reduce scope: one `--platform`, no groups  
3. Compare permissions in [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer)  
4. Redact secrets before sharing logs  
