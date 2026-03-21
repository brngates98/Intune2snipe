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
- **App / Docker:** CI already tags images with semver when you push `v*` tags (see `.github/workflows/docker-build.yml`).
- **Helm chart:** On each release tag, CI runs `helm package` with `--version` and `--app-version` set from the tag so the chart version tracks the app.

## Maintainer: cut a release

1. Ensure `main` is green (tests + Docker build).
2. Pick the next version (e.g. `1.0.0`).
3. Create and push an annotated tag:

   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```

4. The **Release** workflow (`.github/workflows/release.yml`) will:
   - Package the Helm chart with that version
   - Create a GitHub Release with generated notes and attach `intune2snipe-1.0.0.tgz`
   - Push the chart to GHCR as an OCI package (best-effort; see workflow)
   - Deploy **`index.yaml`** to **GitHub Pages** via **Actions** so `helm repo add https://<user>.github.io/<repo>/` stays current (requires [Pages → Source: GitHub Actions](docs/github-pages-helm.md) once)

Docker images are built by the existing workflow on the same tag push.

## Auto-maintenance

- **Images:** Built on every push to `main` and on tags; no manual image build.
- **Chart:** Linted on every PR (`helm lint`). Packaged and published **only** on semver tags via the release workflow—no manual `helm package` for official artifacts.
- **Dependencies:** Dependabot updates Python and Actions; chart template changes are reviewed in normal PRs.
