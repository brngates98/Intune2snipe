# Configuration

## Required environment variables

| Variable | Purpose |
|----------|---------|
| `AZURE_TENANT_ID` | Azure AD tenant directory ID (GUID) |
| `AZURE_CLIENT_ID` | Application (client) ID of the app registration |
| `SNIPEIT_URL` | Snipe-IT base API URL — **HTTPS**; must end with `/api/v1` (the app will append `/api/v1` if you omit it) |
| `SNIPEIT_API_TOKEN` | Snipe-IT personal API token |

## Microsoft Graph authentication (one of)

| Variable | Purpose |
|----------|---------|
| `AZURE_CLIENT_SECRET` | Client secret value (daemon / client credentials) |
| `AZURE_COMBINED_CERT_KEY` | PEM with **certificate + private key** for certificate-based Graph auth |
| `AZURE_CERTIFICATE_PEM` + `AZURE_PRIVATE_KEY_PEM` | Split PEM (combined into one credential internally) |

You must configure **at least one** of the rows above (not a placeholder like `your-...`). If both certificate and secret are present, the app tries **certificate first** and can **fall back** to the secret on failure. See **[Certificate authentication](CERTIFICATE_CONFIG.md)**.

## Other variables

| Variable | Purpose |
|----------|---------|
| `SNIPEIT_DEFAULT_STATUS` | Exact name of an **existing** Snipe-IT status label (case-sensitive); default in code is `Ready to Deploy` |
| `AZURE_GROUP_IDS` | Comma-separated Azure AD **group object IDs** (UUIDs; see [Usage & CLI](usage-and-cli.md)) |
| `SNIPEIT_ALLOW_PRIVATE_IP` | Set to `1` / `true` / `yes` to allow `SNIPEIT_URL` hostnames that resolve to **literal private IPs** (Snipe on `https://10.x.x.x`); internal **DNS names** are unaffected |

You can pass groups via `--groups` on the command line instead of `AZURE_GROUP_IDS`.

## Local `.env` (optional)

If `python-dotenv` is installed (included in `requirements.txt`), a `.env` file in the working directory is loaded automatically. Use **[`.env.example`](../.env.example)** as a template; **never commit** real secrets (`.env` is gitignored).

## External secret stores (optional)

For AWS Secrets Manager, HashiCorp Vault KV, or Azure Key Vault, use CLI flags (see [Usage & CLI](usage-and-cli.md)):

- `--secret-store` with `--secret-name`, `--aws-region`, `--vault-addr`, `--vault-path`, or `--keyvault-url` / `AZURE_KEYVAULT_URL` as needed.

Install the matching optional Python packages in the runtime image or venv (`boto3`, `hvac`, `azure-keyvault-secrets`, etc.). Key Vault secret **names** use hyphens (e.g. `AZURE-CLIENT-SECRET`) and are mapped to underscore env names after fetch.

## Example shell exports

```bash
export AZURE_TENANT_ID="<your-tenant-guid>"
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"

export SNIPEIT_URL="https://my-snipeit.example.com/api/v1"
export SNIPEIT_API_TOKEN="<your-snipeit-api-token>"
export SNIPEIT_DEFAULT_STATUS="Ready to Deploy"

# Optional group filter (each id must be a UUID object id)
export AZURE_GROUP_IDS="<group-object-id-1>,<group-object-id-2>"
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
6. **Certificates & secrets** → create a **client secret** *or* upload a **certificate** for app-only auth (see [Certificate authentication](CERTIFICATE_CONFIG.md))  

## Snipe-IT API token

1. Sign in to Snipe-IT  
2. **My Account** → **API Tokens**  
3. Create a token with permissions appropriate for creating/updating assets and checkout  
4. Store it securely; you may not be able to view it again  

## Security notes

- Do not commit secrets to git  
- Treat the client secret and API token like passwords  
- In Kubernetes, use **Secrets** (or Sealed Secrets / External Secrets / SOPS); see [Deployment — Kubernetes](deployment-kubernetes.md)  
