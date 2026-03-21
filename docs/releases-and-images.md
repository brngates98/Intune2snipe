# Releases and container images

## Why pin a version?

- **`latest`** on GHCR is updated when a maintainer runs a **release** (semver **`v*`** tag) or triggers **workflow_dispatch** for the CI workflow — **not** on every merge to `main`, so the registry is not filled with one image per commit. Prefer a **semver image tag** for production.  
- **Semver tags** (e.g. `1.2.3` from git tag `v1.2.3`) give you a **stable** image and a clear upgrade path.  
- **GitHub Releases** attach the **Helm chart** package (`.tgz`) for the same version when maintainers tag releases.  

**Process:** Requiring **pull requests** before merging to `main` (branch protection) is recommended for review, but it does **not** by itself reduce image count — each merged PR still updates `main`. Release-driven Docker pushes (above) are what limit published images.

## Where artifacts live

| Artifact | Location |
|----------|----------|
| Docker image | `ghcr.io/brngates98/intune2snipe:<tag>` (the only container package; chart is not duplicated to GHCR) |
| Helm chart tarball | [GitHub Releases](https://github.com/brngates98/intune2snipe/releases) (attached `.tgz`) |
| Helm repo index (`helm repo add`) | [GitHub Pages from Actions](github-pages-helm.md) — `https://<user>.github.io/<repo>/index.yaml` |

## Typical production usage

```bash
docker pull ghcr.io/brngates98/intune2snipe:1.2.3
```

```bash
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --set image.tag=1.2.3
```

## Maintainers

Cutting releases, semver rules, and CI behavior: [RELEASING.md](../RELEASING.md).
