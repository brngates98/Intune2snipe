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
- **App / Docker / Helm / Pages:** One workflow (`.github/workflows/docker-build.yml`, **“CI, Docker, and Release”**) runs tests, then builds and pushes the **Docker image** to GHCR, then—**only on `v*` tags**—packages the Helm chart, creates the GitHub Release (`.tgz` asset), and deploys the Helm `index.yaml` to GitHub Pages. The chart is **not** pushed as a second GHCR package; use the Release asset or `helm repo add` from Pages.
- **Helm chart:** On each semver tag, `helm package` uses `--version` and `--app-version` from the tag so the chart matches the image.

## Release notes policy (SemVer)

Releases use tags `vMAJOR.MINOR.PATCH`. Compare the **new** version to the **last published** release to classify the bump.

| Bump | When | Release notes |
|------|------|----------------|
| **Major** | `MAJOR` increases | **Required:** comprehensive notes (committed file; see below) |
| **Minor** | `MINOR` increases, `MAJOR` unchanged | **Required:** comprehensive notes (committed file; see below) |
| **Patch** | Only `PATCH` changes | **Optional:** GitHub auto-generated notes from merged PRs/commits are acceptable; add a committed file if the change needs extra context |

**Comprehensive** means the GitHub Release body is **not** only the auto summary. It must help operators and integrators decide to upgrade. At minimum, include:

- A short **summary** and **highlights** (user-visible behavior).
- **Breaking changes** (or explicitly **None**).
- **Upgrade / migration** steps (config, env vars, CLI, Helm values, or ops runbooks).
- Pointers for **Docker** and **Helm** (image tag, chart version, where to install).
- **Fixes** / notable internals if useful; **known issues** when relevant.

Use the outline in **[`.github/RELEASE_NOTES_TEMPLATE.md`](.github/RELEASE_NOTES_TEMPLATE.md)**. For **major** and **minor** releases, copy it to **`.github/release-notes-<tag>.md`** (example: `.github/release-notes-v1.3.0.md`), fill it in, commit on `main`, **then** tag and push. CI will use that file for the GitHub Release body when it exists; otherwise it falls back to auto-generated notes (appropriate for most **patch** releases).

## Maintainer: cut a release

1. Ensure `main` is green (tests + Docker build).
2. Pick the next version (e.g. `1.0.0`).
3. For a **major** or **minor** release: add and commit `.github/release-notes-vX.Y.Z.md` as above.
4. Create and push an annotated tag:

   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```

5. The same workflow (`.github/workflows/docker-build.yml`) runs, in order:
   - **Test** → **Docker build/push to GHCR** (image tags include the semver from the tag, e.g. `1.0.0`, `latest` on default branch only for non-tag pushes)
   - **Helm:** package chart, GitHub Release + `.tgz` asset, GitHub Pages `index.yaml`
   - **GitHub Pages:** deploy merged `index.yaml` for `helm repo add` (requires [Pages → Source: GitHub Actions](docs/github-pages-helm.md) once)

Because **Helm release runs after Docker push**, the GHCR image for that tag is already published when the GitHub Release is created.

### If **Publish Helm repo (GitHub Pages)** failed on a tag

Older workflow revisions used `environment: github-pages` on the Pages job. GitHub’s **github-pages** environment often allows only **branch** deployments, so **tag** workflows were rejected (“Tag `v…` is not allowed to deploy to github-pages”). That is fixed on `main` by **not** attaching that job to the protected environment (OIDC + `pages:write` still authorize the deploy).

**Important:** Your **git tag** must point at a commit **on or after** that workflow change. If you already pushed `v0.0.1` before the fix, move the tag to current `main` and push again (you may need bypass if [tag rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets-for-repositories) restrict tag updates):

```bash
git pull origin main
git push origin :refs/tags/v0.0.1   # omit if you never pushed the tag
git tag -d v0.0.1
git tag -a v0.0.1 -m "Release v0.0.1"
git push origin v0.0.1
```

If a **GitHub Release** for that tag already exists and `action-gh-release` errors, delete the release in the UI (or `gh release delete v0.0.1`) and re-run the workflow or push the tag again.

## Auto-maintenance

- **Images:** **Not** built or pushed on ordinary merges to `main` (so every PR merge does not publish a new GHCR image). Docker images are **built and pushed** when you push a **semver tag** (`v*`) or run **Actions → “CI, Docker, and Release” → Run workflow** (`workflow_dispatch`), which can refresh `:latest`. **PRs** that change application code still **build** the image in CI (without pushing) to validate the `Dockerfile`. Documentation-only commits are skipped for Docker via the `paths` filter on the `test` job’s dependency chain where applicable. **Semver tags** always run the full release pipeline (Docker + Helm + Pages), including when the tagged commit is docs-only.
- **Chart:** Linted on every PR (`helm lint`). Packaged and published **only** on semver tags in the same workflow as Docker—no manual `helm package` for official artifacts.
- **Dependencies:** Dependabot updates Python and Actions; chart template changes are reviewed in normal PRs.
