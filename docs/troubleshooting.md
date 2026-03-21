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
