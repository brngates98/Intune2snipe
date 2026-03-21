# Getting started

## What you need

- **Python 3.11+** *or* **Docker** (no local Python required)
- An **Azure AD app registration** (application permissions) and **Snipe-IT** with API access  
  Details: [Configuration](configuration.md)
- **Admin consent** in Azure AD for the app permissions you use

## Install (choose one)

### Option A — Run from source (regular Python script)

Use a normal Python 3.11+ environment on your machine: clone the repo, create a **virtualenv**, install dependencies with `pip`, set [environment variables](configuration.md), then run `python3 app.py` (same entrypoint as Docker). Step-by-step instructions—including Windows venv commands, cron examples, and development installs—are in **[Run locally with Python](run-local-python.md)**.

Quick version:

```bash
git clone https://github.com/brngates98/intune2snipe.git
cd intune2snipe
python3 -m venv .venv && source .venv/bin/activate   # see run-local-python.md for Windows
pip install -r requirements.txt
# export AZURE_* and SNIPEIT_* (see Configuration)
python3 app.py --dry-run --platform windows
```

### Option B — Pull the container image

```bash
docker pull ghcr.io/brngates98/intune2snipe:latest
```

See [Deployment — Docker](deployment-docker.md) for private GHCR auth and version tags.

## Configure credentials

Set the variables in [Configuration](configuration.md) (Azure tenant/client/secret, Snipe-IT URL and token, default status label).

You can `export` them in your shell or use a `.env` file with your own loader; the app reads **environment variables**.

## First run (safe preview)

Always start with a **dry run** so nothing is written to Snipe-IT:

```bash
python3 app.py --dry-run --platform windows
```

With Docker:

```bash
docker run --rm \
  -e AZURE_TENANT_ID="..." \
  -e AZURE_CLIENT_ID="..." \
  -e AZURE_CLIENT_SECRET="..." \
  -e SNIPEIT_URL="https://your-snipeit.example.com/api/v1" \
  -e SNIPEIT_API_TOKEN="..." \
  -e SNIPEIT_DEFAULT_STATUS="Ready to Deploy" \
  ghcr.io/brngates98/intune2snipe:latest \
  --dry-run --platform windows
```

Review the log output, then run **without** `--dry-run` when you are satisfied.

## Next steps

- [Usage & CLI](usage-and-cli.md) — platforms, groups, examples  
- [Deployment — Kubernetes](deployment-kubernetes.md) — scheduled sync with Helm or `kubectl`  
- [Troubleshooting](troubleshooting.md) — if something fails  
