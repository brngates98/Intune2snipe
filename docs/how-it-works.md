# How it works

## High-level flow

1. **Authenticate** to Microsoft Graph with Azure AD **client credentials** (daemon app).  
2. **Optional group filter** — If `--groups` or `AZURE_GROUP_IDS` is set, collect Azure AD **device** object IDs from those groups (`/groups/{id}/members/microsoft.graph.device`).  
3. **List Intune managed devices** — `GET /deviceManagement/managedDevices` with `$select` (and optional `$filter` by platform).  
4. **Optional primary user** — When `GRAPH_USE_PRIMARY_USER` or `--use-primary-user` is set, resolve assignees via Graph `$batch` to `/beta/deviceManagement/managedDevices/{id}/users`.  
5. **Filter** by `--platform`, excluded management states, optional group membership, and optional stale-device policy.  
6. **Snipe-IT setup** — Ensure category `Intune`, manufacturers, models; **status label** must already exist (`SNIPEIT_DEFAULT_STATUS`).  
7. **Per device** — Find asset by serial (including soft-deleted when configured); **update** or **create** with extended field mapping; **check out** or **check in** as needed.  

## Field mapping

| Intune (managedDevice) | Snipe-IT |
|------------------------|----------|
| `deviceName` | Asset `name` |
| `serialNumber` | Asset `serial` |
| `manufacturer` | Manufacturer / `manufacturer_id` |
| `model` | Model / `model_id` |
| `userPrincipalName` / primary user / `emailAddress` | Normalized UPN → user or location lookup → checkout |
| `managedDeviceOwnerType` = `personal` | Asset `byod` |
| `complianceState` | Optional status via `SNIPEIT_COMPLIANCE_STATUS_MAP` |
| Custom mappings | Snipe custom fields via `SNIPEIT_CF_*` / `SNIPEIT_CUSTOM_FIELDS` |

Android Enterprise UPNs may have a 32-character GUID prefix; the sync strips it before user lookup.

## Checkout target

By default (`SNIPEIT_CHECKOUT_MODE=user`), the app checks assets out to a Snipe-IT **user** matched by **email** or **username** (exact API filters, not fuzzy search). See [Snipe-IT API — users](https://snipe-it.readme.io/reference/users).

When `SNIPEIT_CHECKOUT_MODE=location`, the app takes the first `SNIPEIT_LOCATION_PREFIX_LENGTH` characters of the UPN local part and checks the asset out to the first Snipe-IT **location** whose name starts with that prefix. See [Snipe-IT API — hardware checkout](https://snipe-it.readme.io/reference/hardware-checkout).

Checkout and checkin calls include `status_id` from `SNIPEIT_CHECKOUT_STATUS` / `SNIPEIT_CHECKIN_STATUS` (defaulting to `SNIPEIT_DEFAULT_STATUS`). On create, assignee can be set in the same POST when `SNIPEIT_SKIP_CHECKOUT_ON_CREATE` is not set.

On updates, checkout runs again when the resolved user or location differs; checkin runs when Intune has no primary user or when a stale-device policy applies.

## Group matching and Azure AD

Group filtering compares Intune’s **`azureADDeviceId`** to device IDs returned from group membership (legacy **`azureActiveDeviceId`** is accepted if present). Devices must be properly joined/registered in Azure AD for this to line up.

## Graph query optimization

Device list requests use `$select` to fetch only fields needed for sync. Platform filters use server-side `$filter` on `operatingSystem` when a single platform is selected (`windows`, `ios`, `android`, `macos`); `all` still applies a client-side macOS fallback for `"Mac"` values if Graph filter is not used.
