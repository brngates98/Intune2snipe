# How it works

## High-level flow

1. **Authenticate** to Microsoft Graph with Azure AD **client credentials** (daemon app).  
2. **Optional group filter** — If `--groups` or `AZURE_GROUP_IDS` is set, collect Azure AD **device** object IDs from those groups (`/groups/{id}/members/microsoft.graph.device`).  
3. **List Intune managed devices** — `GET /deviceManagement/managedDevices` (paginated).  
4. **Filter** by `--platform` and, if configured, by membership in the device ID set from step 2.  
5. **Snipe-IT setup** — Ensure category `Intune`, manufacturers, models; **status label** must already exist (`SNIPEIT_DEFAULT_STATUS`).  
6. **Per device** — Find asset by serial; **update** or **create**; optionally **check out** to a Snipe user or location derived from the Intune primary user.  

## Field mapping

| Intune (managedDevice) | Snipe-IT |
|------------------------|----------|
| `deviceName` | Asset `name` |
| `serialNumber` | Asset `serial` |
| `manufacturer` | Manufacturer / `manufacturer_id` |
| `model` | Model / `model_id` |
| `userPrincipalName` | Normalized UPN → user or location lookup → checkout |

Android Enterprise UPNs may have a 32-character GUID prefix; the sync strips it before user lookup.

## Checkout target

By default (`SNIPEIT_CHECKOUT_MODE=user`), the app checks assets out to a Snipe-IT **user** matched by **email** or **username** (exact API filters, not fuzzy search). See [Snipe-IT API — users](https://snipe-it.readme.io/reference/users).

When `SNIPEIT_CHECKOUT_MODE=location`, the app takes the first `SNIPEIT_LOCATION_PREFIX_LENGTH` characters of the UPN local part (for example `A55` from `A55@domain.com`) and checks the asset out to the first Snipe-IT **location** whose name starts with that prefix (for example `A55 - somewhere`). See [Snipe-IT API — hardware checkout](https://snipe-it.readme.io/reference/hardware-checkout).

On updates, checkout runs again when the resolved user or location differs from what is already on the asset.

## Group matching and Azure AD

Group filtering compares Intune’s **`azureADDeviceId`** to device IDs returned from group membership (legacy **`azureActiveDeviceId`** is accepted if present). Devices must be properly joined/registered in Azure AD for this to line up.
