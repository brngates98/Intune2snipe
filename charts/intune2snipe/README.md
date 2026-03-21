# intune2snipe Helm chart

Deploys the [Intune2snipe](https://github.com/brngates98/intune2snipe) sync as a `CronJob`.

**User-facing documentation:** [Documentation hub](../../docs/README.md) · [Kubernetes deployment](../../docs/deployment-kubernetes.md) · [Enable GitHub Pages for `helm repo add`](../../docs/github-pages-helm.md)

## Prerequisites

- Kubernetes 1.21+ (CronJob `timeZone` requires 1.27+)
- A `Secret` in the target namespace with the environment variables expected by `app.py` (see [Configuration](../../docs/configuration.md)). The chart references it by **`secrets.existingSecret`** (default `intune2snipe-secrets`).

## Install from the GitHub-hosted Helm repo

After [setting Pages → Source to **GitHub Actions**](../../docs/github-pages-helm.md):

```bash
helm repo add intune2snipe https://brngates98.github.io/intune2snipe/
helm repo update
helm upgrade --install intune2snipe intune2snipe/intune2snipe --version 1.2.3 \
  --namespace intune2snipe --create-namespace
```

## Install from a git checkout path

```bash
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --namespace intune2snipe --create-namespace \
  --set image.tag=1.2.3
```

Use an image tag that matches a [GitHub Release](https://github.com/brngates98/intune2snipe/releases) / GHCR tag (not only `:latest` in production).

## Values overview

Structured sections in `values.yaml`:

| Section | Purpose |
|---------|---------|
| **`sync`** | CLI behavior: `dryRun`, `platform`, `groups`, `extraArgs` |
| **`cronjob`** | Schedule, `timeZone`, `suspend`, history limits, job metadata |
| **`image`** | `repository`, `tag`, `digest`, `pullPolicy` |
| **`pod`** | Pod `annotations` and `labels` |
| **`podSecurityContext` / `containerSecurityContext`** | Pod and container security contexts |
| **`resources`** | CPU/memory requests and limits |
| **`nodeSelector` / `tolerations` / `affinity`** | Scheduling |
| **`priorityClassName`** | Optional PriorityClass |
| **`secrets.existingSecret`** | Name of the Secret holding Azure + Snipe env vars |
| **`imagePullSecrets`** | Registry pull secrets (e.g. private GHCR) |

### Common overrides

```bash
# Windows only, dry-run, custom schedule
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --set sync.platform=windows \
  --set sync.dryRun=true \
  --set cronjob.schedule="0 */6 * * *" \
  --set secrets.existingSecret=my-secret
```

See **`values.yaml`** for every key and defaults.

## OCI registry (optional)

Released chart packages may be published to GHCR as OCI artifacts; see [RELEASING.md](../../RELEASING.md).
