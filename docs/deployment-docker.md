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

- **`latest`** — convenient for testing; moves with the default branch  
- **`main`**, branch names — CI publishes these  
- **`v1.0.0`** (semver git tags) — **recommended for production** pinning  
- **Git SHA** tags — reproducible builds  

See [Releases & images](releases-and-images.md) for how this ties to GitHub Releases.

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
