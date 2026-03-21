# Intune2snipe — agent / AI context

This repository is a **small, focused integration**: a Python CLI (`app.py`) that syncs **Microsoft Intune** managed devices into **Snipe-IT** asset management using documented REST APIs.

## What this project is

- **Language / runtime:** Python 3.11+ (see `Dockerfile`).
- **Entry point:** `app.py` — no framework; `argparse`, `logging`, `requests`, `msal`.
- **Microsoft side:** [Microsoft Graph](https://learn.microsoft.com/en-us/graph/overview) — client credentials (daemon app) against `https://graph.microsoft.com`. Primary calls:
  - `GET /deviceManagement/managedDevices` (paginated)
  - Optional group filter: `GET /groups/{id}/members/microsoft.graph.device` (OData cast)
- **Snipe-IT side:** Snipe-IT REST API under `SNIPEIT_URL` (must end with `/api/v1`). User resolution uses **equality** query params `email` and `username` on `GET /users`, not fuzzy `search`.
- **Tests:** `pytest` in `tests/`; CI runs tests + `helm lint`, then Docker build/push; on `v*` tags the same workflow continues with Helm package, GitHub Release, and Pages (`.github/workflows/docker-build.yml`).
- **Deploy:** Docker image on GHCR; Helm chart in `charts/intune2snipe`; semver tags (`v1.2.3`) run [RELEASING.md](RELEASING.md) (GitHub Release `.tgz`, optional OCI, **`index.yaml` via GitHub Pages + Actions** for `helm repo add` after [Pages source is set to Actions](docs/github-pages-helm.md)).
- **Dependencies:** Pinned in `requirements.txt`; dev deps in `requirements-dev.txt`.

## Conventions for changes

- Prefer **minimal diffs**; match existing style in `app.py` (sections, logging, type hints).
- **Do not** log or commit secrets (Azure client secret, Snipe API token, tenant IDs in examples).
- When changing API behavior, cite or verify against **current** Microsoft Graph and Snipe-IT API docs (links in `app.py` module docstring).
- Run `python -m pytest tests/ -v` before committing.

## Issue workflow

Templates live in `.github/ISSUE_TEMPLATE/`. Labels **BUG**, **TODO**, **ENHANCEMENT**, **FEATURE REQUEST** must exist on the repo (see `.github/LABELS.md`).

## Related docs

- **[docs/README.md](docs/README.md)** — navigable documentation hub for end users.
- [README.md](README.md) — short project overview and links into `docs/`.
- [.github/LABELS.md](.github/LABELS.md) — creating GitHub labels.
