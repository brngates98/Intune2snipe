# Intune2snipe — agent / AI context

This repository is a **small, focused integration**: a Python CLI (`app.py`) that syncs **Microsoft Intune** managed devices into **Snipe-IT** asset management using documented REST APIs.

## What this project is

- **Language / runtime:** Python 3.11+ (see `Dockerfile`).
- **Entry point:** `app.py` — no framework; `argparse`, `logging`, `requests`, `msal`.
- **Microsoft side:** [Microsoft Graph](https://learn.microsoft.com/en-us/graph/overview) — client credentials (daemon app) against `https://graph.microsoft.com`. Primary calls:
  - `GET /deviceManagement/managedDevices` (paginated)
  - Optional group filter: `GET /groups/{id}/members/microsoft.graph.device` (OData cast)
- **Snipe-IT side:** Snipe-IT REST API under `SNIPEIT_URL` (must end with `/api/v1`). User resolution uses **equality** query params `email` and `username` on `GET /users`, not fuzzy `search`.
- **Tests:** `pytest` in `tests/`; CI runs tests + `helm lint` before Docker build (`.github/workflows/docker-build.yml`).
- **Deploy:** Docker image on GHCR; optional Helm chart in `charts/intune2snipe` (see chart README). Semver git tags (`v1.2.3`) trigger [RELEASING.md](RELEASING.md) (packaged chart + GitHub Release; optional OCI push to GHCR).
- **Dependencies:** Pinned in `requirements.txt`; dev deps in `requirements-dev.txt`.

## Conventions for changes

- Prefer **minimal diffs**; match existing style in `app.py` (sections, logging, type hints).
- **Do not** log or commit secrets (Azure client secret, Snipe API token, tenant IDs in examples).
- When changing API behavior, cite or verify against **current** Microsoft Graph and Snipe-IT API docs (links in `app.py` module docstring).
- Run `python -m pytest tests/ -v` before committing.

## Issue workflow

Templates live in `.github/ISSUE_TEMPLATE/`. Labels **BUG**, **TODO**, **ENHANCEMENT**, **FEATURE REQUEST** must exist on the repo (see `.github/LABELS.md`).

## Related docs

- [README.md](README.md) — user-facing install, env vars, Docker/Kubernetes.
- [.github/LABELS.md](.github/LABELS.md) — creating GitHub labels.
