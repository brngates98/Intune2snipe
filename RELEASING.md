# Releases and versioning

End-user context on tags and images: **[docs/releases-and-images.md](docs/releases-and-images.md)**.  
Helm `helm repo add` from this GitHub repo: **[docs/github-pages-helm.md](docs/github-pages-helm.md)** (enable Pages once).

## Why tag releases if we already push Docker images?

- **Traceability:** A [GitHub Release](https://github.com/brngates98/intune2snipe/releases) ties a git tag, changelog, and artifacts to the exact image digest users run.
- **SemVer communication:** Consumers know whether a tag is breaking vs patch (`v2.0.0` vs `v1.0.1`).
- **Helm chart:** The packaged chart (`.tgz`) can use the **same version** as the app, so `helm install` with `--version 1.2.3` matches `image: …:1.2.3`.
- **Supply chain:** Release assets + SBOM (future) are easier to anchor to a version than “whatever `latest` was that day.”

`latest` remains convenient for development; production should pin **image tag** and **chart version**.

## Version scheme

- Use **Semantic Versioning**: `vMAJOR.MINOR.PATCH` on git tags (leading `v` is convention only).
- **App / Docker / Helm / Pages:** One workflow (`.github/workflows/docker-build.yml`, **“CI, Docker, and Release”**) runs tests, then builds and pushes the Docker image, then—**only on `v*` tags**—packages the Helm chart, creates the GitHub Release, pushes the chart OCI (optional), and deploys the Helm `index.yaml` to GitHub Pages.
- **Helm chart:** On each semver tag, `helm package` uses `--version` and `--app-version` from the tag so the chart matches the image.

## Maintainer: cut a release

1. Ensure `main` is green (tests + Docker build).
2. Pick the next version (e.g. `1.0.0`).
3. Create and push an annotated tag:

   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```

4. The same workflow (`.github/workflows/docker-build.yml`) runs, in order:
   - **Test** → **Docker build/push to GHCR** (image tags include the semver from the tag, e.g. `1.0.0`, `latest` on default branch only for non-tag pushes)
   - **Helm:** package chart, GitHub Release + `.tgz` asset, optional OCI push to GHCR
   - **GitHub Pages:** deploy merged `index.yaml` for `helm repo add` (requires [Pages → Source: GitHub Actions](docs/github-pages-helm.md) once)

Because **Helm release runs after Docker push**, the GHCR image for that tag is already published when the GitHub Release is created.

## Auto-maintenance

- **Images:** Built on every push to `main` and on tags; no manual image build.
- **Chart:** Linted on every PR (`helm lint`). Packaged and published **only** on semver tags in the same workflow as Docker—no manual `helm package` for official artifacts.
- **Dependencies:** Dependabot updates Python and Actions; chart template changes are reviewed in normal PRs.
