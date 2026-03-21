# How it works

## High-level flow

1. **Authenticate** to Microsoft Graph with Azure AD **client credentials** (daemon app).  
2. **Optional group filter** — If `--groups` or `AZURE_GROUP_IDS` is set, collect Azure AD **device** object IDs from those groups (`/groups/{id}/members/microsoft.graph.device`).  
3. **List Intune managed devices** — `GET /deviceManagement/managedDevices` (paginated).  
4. **Filter** by `--platform` and, if configured, by membership in the device ID set from step 2.  
5. **Snipe-IT setup** — Ensure category `Intune`, manufacturers, models; **status label** must already exist (`SNIPEIT_DEFAULT_STATUS`).  
6. **Per device** — Find asset by serial; **update** or **create**; optionally **check out** to a Snipe user matched by **email** or **username** (exact API filters, not fuzzy search).  

## Field mapping

| Intune (managedDevice) | Snipe-IT |
|------------------------|----------|
| `deviceName` | Asset `name` |
| `serialNumber` | Asset `serial` |
| `manufacturer` | Manufacturer / `manufacturer_id` |
| `model` | Model / `model_id` |
| `userPrincipalName` | Normalized UPN → user lookup → checkout |

Android Enterprise UPNs may have a 32-character GUID prefix; the sync strips it before user lookup.

## User matching in Snipe-IT

The app uses Snipe-IT `GET /users` with **`email`** and **`username`** query parameters (equality), not the generic `search` parameter. See [Snipe-IT API — users](https://snipe-it.readme.io/reference/users).

## Group matching and Azure AD

Group filtering compares Intune’s **`azureADDeviceId`** to device IDs returned from group membership (legacy **`azureActiveDeviceId`** is accepted if present). Devices must be properly joined/registered in Azure AD for this to line up.
