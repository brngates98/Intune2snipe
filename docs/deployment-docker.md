# Deployment — Docker

Test with Python or `docker run` **before** scheduling long-running or cluster deployments.

## Pull a pre-built image

Images are published to GitHub Container Registry (GHCR):

```bash
docker pull ghcr.io/brngates98/intune2snipe:latest
```

Replace `brngates98/intune2snipe` if you fork or publish under another org: `ghcr.io/<org-or-user>/<repo>:<tag>`.

### Private package

Create a [Personal Access Token](https://github.com/settings/tokens) with `read:packages`, then:

```bash
docker login ghcr.io -u YOUR_GITHUB_USERNAME
# paste PAT when prompted
```

Or non-interactive:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u USERNAME --password-stdin
```

## Image tags

- **`v1.0.0`** (semver from git tags `v1.0.0`) — **recommended for production**; CI **pushes** images when you push a **`v*`** tag (see [RELEASING.md](../RELEASING.md)).  
- **`latest`** — updated when a release runs (same **`v*`** workflow) or when a maintainer runs the **CI, Docker, and Release** workflow manually (**workflow_dispatch**). It is **not** updated on every merge to `main`.  
- **Semver rolling tags** — e.g. `1`, `1.2` from the same release job when using semver patterns.  
- **Git SHA** — attached to **tag** builds for reproducibility; ordinary `main` merges do not publish a new image.  

See [Releases & images](releases-and-images.md) for how this ties to GitHub Releases.

## Process user

The image runs as a **non-root** user (`appuser`, UID **10001**). If you bind-mount files or set `securityContext` in Kubernetes, align ownership and permissions with that UID.

## Run the container

Pass [configuration](configuration.md) via `-e` (and optional CLI args after the image):

```bash
docker run --rm \
  -e AZURE_TENANT_ID="<tenant-id>" \
  -e AZURE_CLIENT_ID="<client-id>" \
  -e AZURE_CLIENT_SECRET="<client-secret>" \
  -e SNIPEIT_URL="https://your-snipeit-url/api/v1" \
  -e SNIPEIT_API_TOKEN="<token>" \
  -e SNIPEIT_DEFAULT_STATUS="Ready to Deploy" \
  ghcr.io/brngates98/intune2snipe:latest \
  --platform windows --dry-run
```

## Build locally

```bash
git clone https://github.com/brngates98/intune2snipe.git
cd intune2snipe
docker build -t intune2snipe:local .
docker run --rm -e ... intune2snipe:local --dry-run
```

## Where to find images on GitHub

- Repository → **Packages** (sidebar), or  
- `https://github.com/<org>/<repo>/pkgs/container/<name>`  
