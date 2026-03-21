# Intune → Snipe-IT Sync

Sync **Microsoft Intune** managed devices into **Snipe-IT** with optional filters by **platform** and **Azure AD group**. Ships as a Python CLI, Docker image on GHCR, and Kubernetes **CronJob** (plain YAML or **Helm**).

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/brngates98/intune2snipe/pkgs/container/intune2snipe)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Documentation (start here)

**Full, navigable docs:** **[`docs/README.md`](docs/README.md)** — table of contents for all user guides.

| Topic | Link |
|--------|------|
| First-time setup & dry run | [Getting started](docs/getting-started.md) |
| Environment variables & Azure / Snipe setup | [Configuration](docs/configuration.md) |
| CLI flags, examples, group IDs | [Usage & CLI](docs/usage-and-cli.md) |
| Docker pull, run, tags | [Deployment — Docker](docs/deployment-docker.md) |
| Helm & Kubernetes manifest | [Deployment — Kubernetes](docs/deployment-kubernetes.md) |
| `helm repo add` (index on GitHub Pages) | [GitHub Pages for Helm](docs/github-pages-helm.md) |
| Sync behavior & field mapping | [How it works](docs/how-it-works.md) |
| Common errors | [Troubleshooting](docs/troubleshooting.md) |
| Version pins & GHCR | [Releases & images](docs/releases-and-images.md) |

---

## Features

- Fetch Intune devices via **Microsoft Graph**; filter by **OS** (`windows`, `android`, `ios`, `macos`, `all`)
- Optional filter by **Azure AD group** membership
- Normalize Android Enterprise **UPN** prefixes; auto-create Snipe **categories / manufacturers / models**
- Create or update assets; **check out** to Snipe users matched by **email** / **username**
- **`--dry-run`**; Docker on **GHCR**; **Helm** chart + plain `k8s/` manifest

---

## Quick start

1. Complete prerequisites and credentials: **[Configuration](docs/configuration.md)**  
2. Run a safe preview: `python3 app.py --dry-run --platform windows` (see **[Getting started](docs/getting-started.md)**)  
3. Schedule in-cluster if needed: **[Deployment — Kubernetes](docs/deployment-kubernetes.md)**  

---

## Repository layout

| Path | Purpose |
|------|---------|
| [`docs/`](docs/) | **User documentation** (navigable hub) |
| [`app.py`](app.py) | Application entrypoint |
| [`charts/intune2snipe/`](charts/intune2snipe/) | Helm chart |
| [`k8s/cronjob.yaml`](k8s/cronjob.yaml) | Sample CronJob + Secret |
| [`RELEASING.md`](RELEASING.md) | Maintainer release process |
| [`AGENTS.md`](AGENTS.md) | Context for AI / automation tools |

---

## Contributing

Issues: [templates](.github/ISSUE_TEMPLATE/) — create labels once per [`.github/LABELS.md`](.github/LABELS.md).  
Before a PR: `pip install -r requirements.txt -r requirements-dev.txt` and `pytest tests/ -v`; test with `--dry-run` where relevant.

---

## License

[MIT License](LICENSE).

---

## Support

[Troubleshooting](docs/troubleshooting.md) · [Open an issue](https://github.com/brngates98/intune2snipe/issues)
