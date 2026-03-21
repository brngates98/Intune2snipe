# Certificate authentication (Microsoft Graph)

The sync can authenticate to Microsoft Graph with either:

1. **Client secret** — `AZURE_CLIENT_SECRET` (same as classic daemon / app-only flows), or  
2. **X.509 certificate** — PEM material in environment variables, using `azure.identity.CertificateCredential` under the hood.

You may configure **both**; if certificate acquisition fails, the app can **fall back** to the client secret when `AZURE_CLIENT_SECRET` is set.

## App registration steps (high level)

1. In **Microsoft Entra ID** → **App registrations** → your app → **Certificates & secrets**.  
2. Upload the **public** certificate (CER) or create a certificate credential.  
3. Ensure **Application** permissions for Graph are granted (same as for client-secret auth), e.g. `DeviceManagementManagedDevices.Read.All`, and admin consent where required.  
4. Map the **same app (client) ID** and tenant to the environment variables used by this project.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `AZURE_COMBINED_CERT_KEY` | Single PEM string containing **both** the certificate and private key (`BEGIN CERTIFICATE` / `BEGIN PRIVATE KEY` blocks). |
| `AZURE_CERTIFICATE_PEM` + `AZURE_PRIVATE_KEY_PEM` | Alternative: certificate and key in **two** variables; the app concatenates them. |

Placeholders like `your-...` are treated as unset (see [Configuration](configuration.md)).

## Kubernetes / Docker

Mount PEM content from a **Secret** (or External Secrets / CSI driver) and expose it as one or two env vars, or use a secret store loader (`--secret-store`) so credentials are injected at runtime.

## References

- [Microsoft identity platform application authentication — certificate credentials](https://learn.microsoft.com/en-us/entra/identity-platform/howto-create-service-principal-portal)  
- [Microsoft Graph auth overview](https://learn.microsoft.com/en-us/graph/auth/auth-concepts)
