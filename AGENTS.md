# Intune2snipe — agent / AI context

This repository is a **small, focused integration**: a Python CLI (`app.py`) that syncs **Microsoft Intune** managed devices into **Snipe-IT** asset management using documented REST APIs.

## What this project is

- **Language / runtime:** Python 3.11+ (see `Dockerfile`).
- **Entry point:** `app.py` — no framework; `argparse`, `logging`, `requests`, `msal`.
- **Tests:** `pytest` in `tests/`; CI runs tests + `helm lint`, then Docker build/push; on `v*` tags the same workflow continues with Helm package, GitHub Release, and Pages (`.github/workflows/docker-build.yml`).

### Microsoft Graph & Intune (source of truth)

- **Product:** [Microsoft Intune](https://learn.microsoft.com/en-us/mem/intune/) managed devices (MDM) exposed through **[Microsoft Graph](https://learn.microsoft.com/en-us/graph/overview)** — not the legacy Intune Silverlight APIs.
- **Auth:** Azure AD **app registration** with **client credentials** (daemon / no user). MSAL `ConfidentialClientApplication` acquires a token with scope **`https://graph.microsoft.com/.default`**. Required env: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (see [Configuration](docs/configuration.md)).
- **Permissions (typical):** `DeviceManagementManagedDevices.Read.All`; **`DeviceManagementServiceConfig.Read.All`** for automatic Windows Autopilot lookup; group filtering needs `GroupMember.Read.All` or `Group.Read.All`; user-related flows may need `User.Read.All`. Admin consent required.
- **Data read:** Primary endpoint is **[List managedDevices](https://learn.microsoft.com/en-us/graph/api/intune-devices-manageddevice-list)** (`GET https://graph.microsoft.com/v1.0/deviceManagement/managedDevices`). Responses are **paginated** via `@odata.nextLink`; the code must follow next links until exhausted. Optional `$filter` on `operatingSystem` (Windows/Android/iOS/macOS) when the CLI `--platform` is not `all`.
- **Windows Autopilot:** When `--platform` is `windows` or `all`, also **[List windowsAutopilotDeviceIdentities](https://learn.microsoft.com/en-us/graph/api/intune-enrollment-windowsautopilotdeviceidentity-list)** (unless `SNIPEIT_SKIP_AUTOPILOT=true`). Used for lifecycle **Pending Autopilot** when a serial leaves Intune but remains in Autopilot after wipe.
- **Lifecycle reconciliation:** With **`SYNC_STATE_FILE`**, serials absent from Intune vs the prior run → **Pending Autopilot** (Windows + Autopilot pending states) or **Archived**. Retire/wipe `managementState` → check in + **Pending Retire**. Requires Snipe status labels and restore-before-update for soft-deleted assets.
- **Group filter:** If `--groups` or `AZURE_GROUP_IDS` is set, devices are restricted to members of those Azure AD groups. Implementation uses **[List group members](https://learn.microsoft.com/en-us/graph/api/group-list-members)** with an **OData cast** to `microsoft.graph.device` (see [group members](https://learn.microsoft.com/en-us/graph/api/group-list-members) and `Microsoft.Graph.Device` member type). Device IDs are intersected with the full managed-device list.
- **Token lifecycle:** Access tokens expire; the client refreshes before expiry (skew buffer) so long syncs do not fail mid-pagination with HTTP 401.
- **Canonical docs in code:** `app.py` module docstring links to Graph and Snipe-IT reference pages — **prefer those URLs** when validating or changing API behavior.

### Snipe-IT (target system)

- **Product:** [Snipe-IT](https://snipeitapp.com/) open-source IT asset management. This app treats it as the **CMDB** for hardware records.
- **API:** REST base URL **`SNIPEIT_URL` must end with `/api/v1`** (see [Configuration](docs/configuration.md)). Authentication is a **Bearer** API token (`SNIPEIT_API_TOKEN`); headers `Accept`/`Content-Type: application/json`.
- **Assets:** Create/update **`/hardware`**; look up by serial via **`/hardware/byserial`**. Default **status** must match an **existing** status label name (`SNIPEIT_DEFAULT_STATUS`) — the app resolves name → id via **`/statuslabels`**. Lifecycle statuses: **Pending Autopilot**, **Pending Retire**, **Archived** (configurable via `SNIPEIT_STATUS_*`). Soft-deleted assets: **`POST /hardware/{id}/restore`** before update.
- **Taxonomy:** May create or resolve **categories**, **manufacturers**, and **models** (`/categories`, `/manufacturers`, `/models`) so new assets align with Snipe models.
- **Checkout:** Assigns assets to Snipe users via **`POST /hardware/{id}/checkout`** when a managed device user can be mapped.
- **User resolution (critical):** Snipe **users** are resolved with **`GET /users?email=`** or **`GET /users?username=`** — **exact equality** filters (Snipe’s `WHERE` match), **not** the generic `search=` parameter. Do not assume fuzzy search. UPNs from Graph may be normalized (e.g. Android Enterprise GUID prefix stripped) before lookup.
- **Snipe API reference:** [Snipe-IT API docs](https://snipe-it.readme.io/reference/users) (users; other endpoints under same doc set).

- **Deploy:** Docker image on GHCR (`ghcr.io/<owner>/intune2snipe`); Helm chart in `charts/intune2snipe`; semver tags (`v1.2.3`) run [RELEASING.md](RELEASING.md) (GitHub Release `.tgz`, **`index.yaml` via GitHub Pages + Actions** for `helm repo add` after [Pages source is set to Actions](docs/github-pages-helm.md)).
- **Dependencies:** Pinned in `requirements.txt`; dev deps in `requirements-dev.txt`.

## Releases

- **Major** and **minor** semver bumps (`v…` tag vs prior release) must ship **comprehensive** GitHub Release notes: commit `.github/release-notes-<tag>.md` before tagging (see **[`RELEASING.md`](RELEASING.md)** and **[`.github/RELEASE_NOTES_TEMPLATE.md`](.github/RELEASE_NOTES_TEMPLATE.md)**). **Patch** releases may rely on auto-generated notes unless extra detail is needed.

## Conventions for changes

- Prefer **minimal diffs**; match existing style in `app.py` (sections, logging, type hints).
- **Do not** log or commit secrets (Azure client secret, Snipe API token, tenant IDs in examples).
- When changing API behavior, cite or verify against **current** Microsoft Graph and Snipe-IT API docs (links in `app.py` module docstring).
- Run `python -m pytest tests/ -v` before committing.

## Issue workflow

Templates live in `.github/ISSUE_TEMPLATE/`. Labels **BUG**, **TODO**, **ENHANCEMENT**, **FEATURE REQUEST** must exist on the repo (see `.github/LABELS.md`).

## Related docs

- **[docs/README.md](docs/README.md)** — navigable documentation hub for end users.
- **[docs/run-local-python.md](docs/run-local-python.md)** — run `app.py` with venv on a workstation (no container).
- **[docs/configuration.md](docs/configuration.md)** — env vars, Azure app permissions, Snipe API token.
- **[docs/how-it-works.md](docs/how-it-works.md)** — sync flow overview.
- [README.md](README.md) — short project overview and links into `docs/`.
- [.github/LABELS.md](.github/LABELS.md) — creating GitHub labels.
