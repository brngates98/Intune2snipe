# Enable GitHub Pages for the Helm repository

The Helm **`index.yaml`** is built and deployed by the **CI, Docker, and Release** workflow (`.github/workflows/docker-build.yml`) after the **Docker image** for the same tag has been pushed to GHCR. It uses the official **GitHub Actions** Pages deployment (`actions/upload-pages-artifact` + `actions/deploy-pages`). Chart `.tgz` files still live on [GitHub Releases](https://github.com/brngates98/intune2snipe/releases); the site only serves **`index.yaml`** (and a small README) so `helm repo add` works.

## One-time: choose “GitHub Actions” as the Pages source

1. Open the repository → **Settings** → **Pages**.  
2. Under **Build and deployment** → **Source**, select **GitHub Actions** (not “Deploy from a branch”).  
3. Save if prompted.

Until this is set, the **Deploy to GitHub Pages** step in that workflow may fail. You do **not** need a `gh-pages` branch for this setup.

After the first successful deploy, your Helm repo URL is typically:

`https://<user>.github.io/<repository>/`

## Verify

```bash
curl -fsSL https://brngates98.github.io/Intune2snipe/index.yaml | head
helm repo add intune2snipe https://brngates98.github.io/Intune2snipe/
helm repo update
```

Use your real **owner** and **repository** name in the URL (GitHub preserves repository name casing in the Pages URL).

**Private repositories:** GitHub Pages for private repos may require a paid plan or GitHub Enterprise; otherwise use chart assets from Releases or install from a [git path](deployment-kubernetes.md).

## Troubleshooting

### “Tag `v…` is not allowed to deploy to github-pages” (environment protection)

The **Publish Helm repo (GitHub Pages)** job uses the **`github-pages`** [environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment). If that environment only allows deployments from **`main`** (or a fixed set of branches), **tag-triggered** runs are rejected.

**Fix (one-time):** Repository → **Settings** → **Environments** → **`github-pages`** → **Deployment branches and tags** → allow tags that match your releases, e.g. **`v*`** (or **All branches and tags**, depending on your security preference). Save, then **re-run failed jobs** on the workflow run or push a new tag.

### Node.js 20 deprecation warnings

Some Actions (e.g. `azure/setup-helm`) may log Node 20 deprecation notices; they are warnings from the runner image, not necessarily a failure. Upgrade action versions when maintainers publish Node 24–compatible releases.

## Why not “Deploy from a branch”?

You *can* publish Pages from a branch (e.g. `gh-pages`), but deploying **from Actions** keeps the Helm index in sync with releases without maintaining an extra branch. The workflow is the single source of truth.
