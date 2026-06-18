# Troubleshooting

## Authentication (Microsoft Graph)

**403 when fetching devices**

- Confirm `DeviceManagementManagedDevices.Read.All` and **admin consent**  
- Confirm the client secret has **not expired**  

**403 when reading groups**

- Add `GroupMember.Read.All` or `Group.Read.All` and grant consent — [List group members](https://learn.microsoft.com/en-us/graph/api/group-list-members)  
- Verify group **object IDs** are correct  

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
