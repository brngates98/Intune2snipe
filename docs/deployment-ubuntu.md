# Deployment — Ubuntu server (Docker or Python + cron)

Run Intune2snipe on a **Linux VM or bare-metal Ubuntu host** without Kubernetes.

## Choose your path

| | |
|--|--|
| **[Option A — Docker + cron](#option-a)** | Pull the **GHCR image** and run with `docker run` (recommended; no local Python). |
| **[Option B — Python script](#option-b)** | Clone the repo and run **`app.py`** with a virtualenv. |

Both paths start with **[shared setup](#shared-setup)** (env file + logs), then follow the steps in your chosen section.

For workstation setup (macOS, Windows), see [Run locally with Python](run-local-python.md). For general Docker reference, see [Deployment — Docker](deployment-docker.md).

---

## What you need

- **Ubuntu 22.04 or 24.04** (or similar Debian-based distro)
- **Outbound HTTPS** to `login.microsoftonline.com`, `graph.microsoft.com`, and your Snipe-IT URL
- Azure AD app registration and Snipe-IT API token — [Configuration](configuration.md)

**Option A** needs **Docker Engine** (no local Python required).  
**Option B** also needs **Python 3.11+** and Git.

The app reads **environment variables only** (no built-in `.env` file loader). Use an env file on disk and pass it to your wrapper script or `docker run --env-file`.

---

<a id="shared-setup"></a>

## Shared setup — credentials and logs

Create one env file both install methods can use. **Do not put secrets directly in crontab.**

```bash
sudo mkdir -p /etc/intune2snipe /var/log/intune2snipe
sudo nano /etc/intune2snipe/env
```

Example contents (replace placeholders — see [Configuration](configuration.md) for the full list):

```bash
AZURE_TENANT_ID="<tenant-guid>"
AZURE_CLIENT_ID="<app-client-id>"
AZURE_CLIENT_SECRET="<client-secret>"

SNIPEIT_URL="https://snipe.example.com/api/v1"
SNIPEIT_API_TOKEN="<api-token>"
SNIPEIT_DEFAULT_STATUS="Ready to Deploy"

# Optional
# AZURE_GROUP_IDS="<group-id-1>,<group-id-2>"
# GRAPH_USE_PRIMARY_USER=true
# SNIPEIT_CHECKOUT_MODE=location
# SNIPEIT_STALE_DAYS=30
```

Lock down the file:

```bash
sudo chmod 600 /etc/intune2snipe/env
sudo chown root:root /etc/intune2snipe/env
```

If cron runs as a non-root user, give that user read access:

```bash
sudo groupadd -f intune2snipe
sudo usermod -aG intune2snipe "$USER"
sudo chown root:intune2snipe /etc/intune2snipe/env
sudo chmod 640 /etc/intune2snipe/env
```

Log directory (used by both options):

```bash
sudo chown "$USER":"$USER" /var/log/intune2snipe
```

If you use **`SYNC_STATE_FILE`**, create a data directory and mount or write there:

```bash
sudo mkdir -p /var/lib/intune2snipe
sudo chown "$USER":"$USER" /var/lib/intune2snipe
```

Add to the env file (both options):

```bash
SYNC_STATE_FILE=/var/lib/intune2snipe/sync-state.json
```

For **Docker (Option A)**, mount that directory in the wrapper script. For **Python (Option B)**, the app writes directly to the path.

---

<a id="option-a"></a>

# Option A — Docker + cron

No Python or Git required on the host — only Docker and the env file from [Shared setup](#shared-setup).

## A1. Install Docker Engine

Official Docker package (Ubuntu):

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io
```

Add your user to the `docker` group so cron can run containers without `sudo` (log out and back in afterward):

```bash
sudo usermod -aG docker "$USER"
```

Verify:

```bash
docker run --rm hello-world
```

## A2. Pull the image

Public image on GHCR (pin a semver tag in production):

```bash
docker pull ghcr.io/brngates98/intune2snipe:0.0.3
```

If the package is private, log in first — see [Deployment — Docker](deployment-docker.md).

## A3. Wrapper script

Docker reads the shared env file with `--env-file`.

```bash
sudo nano /usr/local/bin/intune2snipe-docker-sync
```

```bash
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/etc/intune2snipe/env"
IMAGE="ghcr.io/brngates98/intune2snipe:0.0.3"
DATA_DIR="/var/lib/intune2snipe"
LOG_DIR="/var/log/intune2snipe"

mkdir -p "$LOG_DIR" "$DATA_DIR"

exec docker run --rm \
  --env-file "$ENV_FILE" \
  -v "${DATA_DIR}:${DATA_DIR}" \
  "$IMAGE" \
  "$@"
```

The volume mount lets `SYNC_STATE_FILE=/var/lib/intune2snipe/sync-state.json` persist between runs. Omit `-v` if you do not use sync state.

```bash
sudo chmod 755 /usr/local/bin/intune2snipe-docker-sync
```

## A4. Run once (Docker)

Dry run:

```bash
/usr/local/bin/intune2snipe-docker-sync --dry-run --platform windows
```

Live one-time sync:

```bash
/usr/local/bin/intune2snipe-docker-sync --platform windows
```

CLI args after the image name are passed to `app.py` (same as `python3 app.py …`).

Equivalent manual command (no wrapper):

```bash
docker run --rm \
  --env-file /etc/intune2snipe/env \
  -v /var/lib/intune2snipe:/var/lib/intune2snipe \
  ghcr.io/brngates98/intune2snipe:0.0.3 \
  --dry-run --platform windows
```

## A5. Schedule with cron (Docker)

Use the **Docker wrapper**, not `docker run` inline in crontab (keeps secrets out of cron and makes upgrades one-line changes).

```bash
crontab -e
```

**Daily at 02:00:**

```cron
0 2 * * * /usr/local/bin/intune2snipe-docker-sync >> /var/log/intune2snipe/sync.log 2>&1
```

**Every 6 hours, Windows only:**

```cron
0 */6 * * * /usr/local/bin/intune2snipe-docker-sync --platform windows >> /var/log/intune2snipe/sync.log 2>&1
```

**Weekly Sunday 03:00 dry-run:**

```cron
0 3 * * 0 /usr/local/bin/intune2snipe-docker-sync --dry-run >> /var/log/intune2snipe/dry-run.log 2>&1
```

Cron runs with a minimal environment — the wrapper handles `--env-file` and image tag.

Verify cron is running:

```bash
systemctl status cron
tail -100 /var/log/intune2snipe/sync.log
```

## A6. Updating (Docker)

Pull the new tag and update the `IMAGE=` line in the wrapper script:

```bash
docker pull ghcr.io/brngates98/intune2snipe:0.0.3
sudo sed -i 's|ghcr.io/brngates98/intune2snipe:.*|ghcr.io/brngates98/intune2snipe:0.0.3"|' /usr/local/bin/intune2snipe-docker-sync
/usr/local/bin/intune2snipe-docker-sync --dry-run
```

---

<a id="option-b"></a>

# Option B — Python script (from source)

## B1. Install system packages

**Ubuntu 24.04** (Python 3.12 is default):

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
python3 --version   # should be 3.11 or newer
```

**Ubuntu 22.04** (default Python may be 3.10 — install 3.11+):

```bash
sudo apt update
sudo apt install -y git software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3-pip
python3.11 --version
```

Use `python3.11` instead of `python3` below if you installed from deadsnakes.

## B2. Install the application

```bash
sudo mkdir -p /opt/intune2snipe
sudo chown "$USER":"$USER" /opt/intune2snipe
git clone https://github.com/brngates98/intune2snipe.git /opt/intune2snipe
cd /opt/intune2snipe

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Pin to a release tag for production:

```bash
cd /opt/intune2snipe
git fetch --tags
git checkout v0.0.3
pip install -r requirements.txt
```

## B3. Wrapper script

Uses the same env file as Option A.

```bash
sudo nano /usr/local/bin/intune2snipe-sync
```

```bash
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/intune2snipe"
ENV_FILE="/etc/intune2snipe/env"
PYTHON="${INSTALL_DIR}/.venv/bin/python"
LOG_DIR="/var/log/intune2snipe"

mkdir -p "$LOG_DIR"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$INSTALL_DIR"
exec "$PYTHON" app.py "$@"
```

```bash
sudo chmod 755 /usr/local/bin/intune2snipe-sync
```

## B4. Run once (Python)

Always start with **`--dry-run`**:

```bash
/usr/local/bin/intune2snipe-sync --dry-run --platform windows
```

When output looks correct, run a **one-time live sync**:

```bash
/usr/local/bin/intune2snipe-sync --platform windows
```

More examples:

```bash
/usr/local/bin/intune2snipe-sync --dry-run
/usr/local/bin/intune2snipe-sync --dry-run --groups "<group-id-1>,<group-id-2>"
/usr/local/bin/intune2snipe-sync --dry-run --use-primary-user
```

## B5. Schedule with cron (Python)

```bash
crontab -e
```

**Daily at 02:00:**

```cron
0 2 * * * /usr/local/bin/intune2snipe-sync >> /var/log/intune2snipe/sync.log 2>&1
```

**Every 6 hours, Windows only:**

```cron
0 */6 * * * /usr/local/bin/intune2snipe-sync --platform windows >> /var/log/intune2snipe/sync.log 2>&1
```

**Weekly Sunday 03:00 dry-run (audit only):**

```cron
0 3 * * 0 /usr/local/bin/intune2snipe-sync --dry-run >> /var/log/intune2snipe/dry-run.log 2>&1
```

## B6. Updating (Python)

```bash
cd /opt/intune2snipe
git fetch --tags
git checkout v0.0.3
source .venv/bin/activate
pip install -r requirements.txt
/usr/local/bin/intune2snipe-sync --dry-run
```

---

## Log rotation (both options)

```bash
sudo nano /etc/logrotate.d/intune2snipe
```

```
/var/log/intune2snipe/*.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

---

## Docker vs Python — quick comparison

| | **Option A — Docker** | **Option B — Python** |
|--|------------------------|------------------------|
| Host Python | Not required | 3.11+ required |
| Wrapper | `/usr/local/bin/intune2snipe-docker-sync` | `/usr/local/bin/intune2snipe-sync` |
| Upgrade | `docker pull` + edit image tag in wrapper | `git checkout` + `pip install` |
| Best when | You want a pinned image and minimal host deps | You already manage Python on the box |

Both use the same `/etc/intune2snipe/env`, cron patterns, and CLI flags.

---

## Troubleshooting

| Symptom | What to check |
|--------|----------------|
| `permission denied` connecting to Docker socket | User in `docker` group; re-login after `usermod` (Option A1) |
| Docker image not found | `docker pull`; GHCR login for private packages |
| `python3: command not found` or wrong version (Python) | Install Python 3.11+ (Option B1) |
| `401` / Graph auth errors | Azure secret, tenant/client, admin consent — [Configuration](configuration.md) |
| Cron job never runs | `grep CRON /var/log/syslog`; script path and execute bit |
| Cron runs but fails silently | Use `>> log 2>&1`; run wrapper manually as the cron user |
| Permission denied on env file | File mode / owner vs user running cron |
| Snipe duplicate assets | Use release with path-based `byserial` lookup (v0.0.2+) |

More detail: [Troubleshooting](troubleshooting.md).

---

## See also

- [Configuration](configuration.md) — env vars, Azure permissions, Snipe token  
- [Usage & CLI](usage-and-cli.md) — `--platform`, `--groups`, `--dry-run`  
- [Deployment — Docker](deployment-docker.md) — GHCR login, image tags  
- [How it works](how-it-works.md) — sync pipeline and field mapping  
- [Releases & images](releases-and-images.md) — version tags
