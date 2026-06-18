# Configuration

## Required environment variables

| Variable | Purpose |
|----------|---------|
| `AZURE_TENANT_ID` | Azure AD tenant directory ID (GUID) |
| `AZURE_CLIENT_ID` | Application (client) ID of the app registration |
| `AZURE_CLIENT_SECRET` | Client secret value |
| `SNIPEIT_URL` | Snipe-IT base API URL — **must end with** `/api/v1` |
| `SNIPEIT_API_TOKEN` | Snipe-IT personal API token |
| `SNIPEIT_DEFAULT_STATUS` | Exact name of an **existing** Snipe-IT status label (case-sensitive) |

## Optional

| Variable | Purpose |
|----------|---------|
| `AZURE_GROUP_IDS` | Comma-separated Azure AD **group object IDs** (see [Usage & CLI](usage-and-cli.md)) |
| `SNIPEIT_CHECKOUT_MODE` | Checkout target: `user` (default) or `location` |
| `SNIPEIT_LOCATION_PREFIX_LENGTH` | When checkout mode is `location`, number of characters taken from the UPN local part before `@` to match a Snipe-IT location name prefix (default: `3`) |

You can also pass groups via `--groups` on the command line instead of this variable.

## Example shell exports

```bash
export AZURE_TENANT_ID="<your-tenant-guid>"
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"

export SNIPEIT_URL="https://my-snipeit.example.com/api/v1"
export SNIPEIT_API_TOKEN="<your-snipeit-api-token>"
export SNIPEIT_DEFAULT_STATUS="Ready to Deploy"

# Optional group filter
export AZURE_GROUP_IDS="<group-id-1>,<group-id-2>"
```

## Azure AD app registration

1. Open [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations**  
2. Create an app or pick an existing one  
3. **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions**  
4. Add at least:
   - `DeviceManagementManagedDevices.Read.All` — [List managedDevices](https://learn.microsoft.com/en-us/graph/api/intune-devices-manageddevice-list)  
   - `User.Read.All` — user lookup for checkout  
   - If you use **group filtering**: `GroupMember.Read.All` or `Group.Read.All` — [List group members](https://learn.microsoft.com/en-us/graph/api/group-list-members)  
5. Click **Grant admin consent** for your tenant  
6. **Certificates & secrets** → create a **client secret** and copy the **value** (not only the ID)  

## Snipe-IT API token

1. Sign in to Snipe-IT  
2. **My Account** → **API Tokens**  
3. Create a token with permissions appropriate for creating/updating assets and checkout  
4. Store it securely; you may not be able to view it again  

## Security notes

- Do not commit secrets to git  
- Treat the client secret and API token like passwords  
- In Kubernetes, use **Secrets** (or Sealed Secrets / External Secrets / SOPS); see [Deployment — Kubernetes](deployment-kubernetes.md)  
