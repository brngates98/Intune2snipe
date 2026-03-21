# intune2snipe Helm chart

Deploys the [Intune2snipe](https://github.com/brngates98/intune2snipe) sync as a `CronJob`.

## Prerequisites

- Kubernetes 1.21+
- A `Secret` in the target namespace with the environment variables expected by `app.py` (see main project [README](../../README.md)). The chart references it by name via `existingSecret` (default `intune2snipe-secrets`).

## Install

```bash
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --namespace intune2snipe --create-namespace \
  --set image.tag=1.2.3
```

Use an image tag that matches a [GitHub Release](https://github.com/brngates98/intune2snipe/releases) / GHCR tag (not only `:latest` in production).

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `image.repository` | `ghcr.io/brngates98/intune2snipe` | Container image |
| `image.tag` | `latest` | Image tag (pin to a semver tag in prod) |
| `cronjob.schedule` | `0 2 * * *` | Cron schedule (UTC) |
| `existingSecret` | `intune2snipe-secrets` | Secret name for env vars |
| `extraArgs` | `[]` | Extra args for `app.py` |
| `resources` | see `values.yaml` | CPU/memory |

## OCI registry (optional)

Released chart packages may be published to GHCR as OCI artifacts; see [RELEASING.md](../../RELEASING.md).
