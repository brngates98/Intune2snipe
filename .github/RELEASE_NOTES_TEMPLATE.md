# Release vX.Y.Z

Use this as a **starting outline** for **major** and **minor** releases. Copy to `.github/release-notes-vX.Y.Z.md` (exact tag name, e.g. `v1.2.0`) and commit it on `main` **before** pushing the tag so CI attaches it to the GitHub Release.

## Summary

One short paragraph: what this release is for and who should care.

## Highlights

- …
- …

## Breaking changes

- … (or **None**)

## Upgrade / migration

- Docker image tag / Helm chart version to use
- Config, env vars, or operational steps users must apply

## Docker and Helm

- Image: `ghcr.io/brngates98/intune2snipe:<version>`
- Helm: chart version aligns with tag; `helm repo add` from GitHub Pages (see `docs/github-pages-helm.md`)

## Fixes and internals

- …

## Known issues

- … (or **None**)
