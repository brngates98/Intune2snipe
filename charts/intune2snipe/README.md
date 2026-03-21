# intune2snipe Helm chart

Deploys the [Intune2snipe](https://github.com/brngates98/intune2snipe) sync as a Kubernetes `CronJob` (Microsoft Intune → Snipe-IT).

**Documentation:** [Docs hub](../../docs/README.md) · [Kubernetes deployment](../../docs/deployment-kubernetes.md) · [Configuration (env vars)](../../docs/configuration.md) · [Helm repo via GitHub Pages](../../docs/github-pages-helm.md)

## Requirements

- **Kubernetes** 1.21+ (`CronJob.spec.timeZone` needs 1.27+ if you set `cronjob.timeZone`)
- **Helm** 3.x
- **Credentials** for Azure and Snipe-IT (see below)

## Credentials

The workload reads the same environment variables as the container image; see [Configuration](../../docs/configuration.md) for semantics.

| Approach | When to use |
|----------|-------------|
| **`secrets.create: true`** | Set **`secrets.stringData.*`** in values (or a separate `-f` file). The chart creates a `Secret`; name is **`secrets.name`** or **`<release-fullname>-secrets`**. |
| **`secrets.create: false`** (default) | Create the `Secret` yourself (`kubectl`, External Secrets, Sealed Secrets, etc.). Point the chart at it with **`secrets.existingSecret`** (default **`intune2snipe-secrets`**). Legacy **`existingSecret`** is still read if **`secrets.existingSecret`** is empty. |

**Secret keys** (whether you create the Secret or the chart does): `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `SNIPEIT_URL`, `SNIPEIT_API_TOKEN`, `SNIPEIT_DEFAULT_STATUS`, and optionally `AZURE_GROUP_IDS` (or use **`sync.groups`** instead of duplicating group IDs in the Secret).

For **certificate-based** Graph authentication (`AZURE_COMBINED_CERT_KEY` or split PEM variables) instead of a client secret, manage the `Secret` yourself (`secrets.create: false`) or add keys via a forked chart—the generated `Secret` template expects `azureClientSecret` today. See [Certificate authentication](../../docs/CERTIFICATE_CONFIG.md).

Do not commit real credentials to git. Prefer a gitignored values file, CI secrets, or a secrets operator in production.

### Example: chart-managed Secret

```yaml
# secrets.local.yaml — add to .gitignore
secrets:
  create: true
  stringData:
    azureTenantId: "00000000-0000-0000-0000-000000000000"
    azureClientId: "your-app-id"
    azureClientSecret: "your-secret"
    snipeitUrl: "https://snipe.example.com/api/v1"
    snipeitApiToken: "your-api-token"
    snipeitDefaultStatus: "Ready to Deploy"
    # azureGroupIds: "guid-1,guid-2"   # optional; omit key or leave empty if unused
```

```bash
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --namespace intune2snipe --create-namespace \
  -f secrets.local.yaml
```

## Versions: chart vs app image

- **Chart version** (`Chart.yaml` / packaged `.tgz`) is what you pass to **`helm install --version`** when using the Helm repo.
- **App / image tag** should match a [release](https://github.com/brngates98/intune2snipe/releases): set **`image.tag`** (or rely on **`Chart.appVersion`** when **`image.tag`** is empty—see `values.yaml`).
- On **`v*`** tags, CI aligns chart and app versions; see [RELEASING.md](../../RELEASING.md).

## Install

### From a git checkout

```bash
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --namespace intune2snipe --create-namespace \
  --set image.tag=1.0.0
```

Pin **`image.tag`** to a release tag in production (avoid relying only on `:latest`).

### From the GitHub Pages Helm repo

[Enable Pages → Source: GitHub Actions](../../docs/github-pages-helm.md) once, then:

```bash
helm repo add intune2snipe https://brngates98.github.io/intune2snipe/
helm repo update
helm search repo intune2snipe --versions
helm upgrade --install intune2snipe intune2snipe/intune2snipe \
  --namespace intune2snipe --create-namespace \
  --version <chart-version-from-search> \
  --set image.tag=<matching-or-desired-app-tag>
```

## Values overview

| Section | Purpose |
|---------|---------|
| **`sync`** | CLI: `dryRun`, `platform`, `groups`, `extraArgs` |
| **`cronjob`** | Schedule, `timeZone`, `suspend`, history limits, job metadata |
| **`image`** | `repository`, `tag`, `digest`, `pullPolicy` |
| **`pod`** | Pod `annotations` and `labels` |
| **`podSecurityContext` / `containerSecurityContext`** | Security contexts |
| **`resources`** | CPU/memory requests and limits |
| **`nodeSelector` / `tolerations` / `affinity`** | Scheduling |
| **`priorityClassName`** | Optional PriorityClass |
| **`secrets.create`** | Create a `Secret` from `secrets.stringData` |
| **`secrets.name`** | Optional fixed name for that `Secret` |
| **`secrets.stringData.*`** | Credential fields when `secrets.create` is true |
| **`secrets.existingSecret`** | Existing `Secret` name when `secrets.create` is false |
| **`existingSecret`** | Deprecated alias for `secrets.existingSecret` |
| **`nameOverride` / `fullnameOverride`** | Helm resource naming |
| **`imagePullSecrets`** | Pull secrets for private registries |

Full defaults and comments: **`values.yaml`**.

### Common `helm` overrides

```bash
# Windows devices only, dry-run, custom schedule, external Secret name
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --set sync.platform=windows \
  --set sync.dryRun=true \
  --set cronjob.schedule="0 */6 * * *" \
  --set secrets.existingSecret=my-external-secret
```

## Lint (maintainers)

```bash
helm lint charts/intune2snipe
helm template test charts/intune2snipe --debug
```

CI runs **`helm lint`** on pull requests.
