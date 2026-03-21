# Run locally with Python

Intune2snipe is a **single script** (`app.py`) with no web server. You can run it on a workstation or jump host with Python 3.11+ the same way you would any other CLI tool.

## Prerequisites

- **Python 3.11 or newer** ([python.org](https://www.python.org/downloads/) or your OS package manager)
- **Azure AD app registration** and **Snipe-IT API access** configured as in [Configuration](configuration.md)

The app reads **environment variables** only (there is no built-in `.env` file loader). Use `export` in your shell, a process manager, or wrap the command with `env VAR=value …`.

## 1. Get the code

```bash
git clone https://github.com/brngates98/intune2snipe.git
cd intune2snipe
```

If you already have a copy of the repo elsewhere, `cd` to that directory instead.

## 2. Create a virtual environment (recommended)

Keeps dependencies isolated from system Python.

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Windows (Command Prompt)**

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Use `deactivate` when you want to leave the venv.

## 3. Configure credentials

Set the variables from [Configuration](configuration.md): `AZURE_*`, `SNIPEIT_URL`, `SNIPEIT_API_TOKEN`, `SNIPEIT_DEFAULT_STATUS`, and optionally `AZURE_GROUP_IDS`.

**Example (Linux / macOS)**

```bash
export AZURE_TENANT_ID="<tenant-guid>"
export AZURE_CLIENT_ID="<app-client-id>"
export AZURE_CLIENT_SECRET="<client-secret>"
export SNIPEIT_URL="https://snipe.example.com/api/v1"
export SNIPEIT_API_TOKEN="<api-token>"
export SNIPEIT_DEFAULT_STATUS="Ready to Deploy"
```

## 4. Run the script

From the repository root (where `app.py` lives), with your venv activated:

```bash
python3 app.py --dry-run --platform windows
```

On some systems the interpreter is `python` instead of `python3`:

```bash
python app.py --dry-run --platform windows
```

Review the logs. When you are ready to write to Snipe-IT, drop `--dry-run`:

```bash
python3 app.py --platform windows
```

All CLI options are documented in [Usage & CLI](usage-and-cli.md).

## Scheduling without Docker or Kubernetes

Use **cron** (Linux/macOS), **Task Scheduler** (Windows), or any job runner that can:

1. Activate the same venv (or call the venv’s `python` by full path).
2. Set the same environment variables (often via a small wrapper script or systemd `EnvironmentFile`).

Example **cron** entry (runs daily at 02:00, logs to a file):

```cron
0 2 * * * cd /path/to/intune2snipe && . .venv/bin/activate && /path/to/intune2snipe/.venv/bin/python app.py >> /var/log/intune2snipe.log 2>&1
```

Prefer loading secrets from a **secure** location your scheduler supports, not plain text in crontab.

## Development dependencies

To run tests locally (optional):

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## See also

- [Getting started](getting-started.md) — overview and first dry run  
- [Configuration](configuration.md) — full variable list and Azure / Snipe setup  
- [Usage & CLI](usage-and-cli.md) — flags and group filters  
- [Troubleshooting](troubleshooting.md) — common errors  
