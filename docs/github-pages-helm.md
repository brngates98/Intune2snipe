# Enable GitHub Pages for the Helm repository

The Helm chart index is published to the **`gh-pages`** branch by CI when you cut a [semver release](../RELEASING.md). For `helm repo add https://<user>.github.io/<repo>/` to work, GitHub must serve that branch as a site.

## Steps (repository admin)

1. Open the repository on GitHub → **Settings** → **Pages** (under *Code and automation*).  
2. Under **Build and deployment** → **Source**, choose **Deploy from a branch**.  
3. **Branch:** `gh-pages`, folder **/ (root)**. Save.  
4. After the next release workflow runs, open **Actions** and confirm the **Release** workflow completed; the site URL (often `https://<user>.github.io/<repo>/`) should show a short README; **`index.yaml`** must be reachable at `https://<user>.github.io/<repo>/index.yaml`.

**Private repositories:** GitHub Pages for private repos may require a paid plan or GitHub Enterprise; otherwise use the chart `.tgz` from [Releases](https://github.com/brngates98/intune2snipe/releases) or install from a [git path](deployment-kubernetes.md).

## Verify

```bash
curl -fsSL https://brngates98.github.io/intune2snipe/index.yaml | head
helm repo add intune2snipe https://brngates98.github.io/intune2snipe/
helm repo update
```

Replace `brngates98/intune2snipe` if you use a fork.
