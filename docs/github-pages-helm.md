# Enable GitHub Pages for the Helm repository

The Helm **`index.yaml`** is built and deployed by the **Release** workflow (`.github/workflows/release.yml`) using the official **GitHub Actions** Pages deployment (`actions/upload-pages-artifact` + `actions/deploy-pages`). Chart `.tgz` files still live on [GitHub Releases](https://github.com/brngates98/intune2snipe/releases); the site only serves **`index.yaml`** (and a small README) so `helm repo add` works.

## One-time: choose “GitHub Actions” as the Pages source

1. Open the repository → **Settings** → **Pages**.  
2. Under **Build and deployment** → **Source**, select **GitHub Actions** (not “Deploy from a branch”).  
3. Save if prompted.

Until this is set, the **Deploy to GitHub Pages** step in the Release workflow may fail. You do **not** need a `gh-pages` branch for this setup.

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

## Why not “Deploy from a branch”?

You *can* publish Pages from a branch (e.g. `gh-pages`), but deploying **from Actions** keeps the Helm index in sync with releases without maintaining an extra branch. The workflow is the single source of truth.
