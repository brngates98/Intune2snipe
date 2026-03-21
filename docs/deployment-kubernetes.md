# Deployment — Kubernetes

Run the sync on a **schedule** (CronJob). Ensure [configuration](configuration.md) is available to the pod as environment variables (usually from a **Secret**).

## Secrets (do not commit real values)

Use one of:

- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)  
- [External Secrets Operator](https://external-secrets.io/)  
- [SOPS](https://github.com/getsops/sops)  
- Or create a standard `Secret` from a secure pipeline  

The Secret must provide the same keys the app expects, for example:

`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `SNIPEIT_URL`, `SNIPEIT_API_TOKEN`, `SNIPEIT_DEFAULT_STATUS`, and optionally `AZURE_GROUP_IDS`.

Alternatively, set **`secrets.create: true`** and **`secrets.stringData`** in the Helm chart so it creates the Secret for you (see [Helm chart README](../charts/intune2snipe/README.md)); do not commit real values to git.

---

## Option 1 — Helm (recommended)

### A — `helm repo add` (chart hosted on this GitHub repo)

After each **semver release**, CI publishes a Helm repository **`index.yaml`** to **GitHub Pages** (via **Actions**) so you can add this repo like any other Helm chart source (packages still live on [GitHub Releases](https://github.com/brngates98/intune2snipe/releases); the index only points to them).

**One-time:** set [GitHub Pages → Source: **GitHub Actions**](github-pages-helm.md) in repository settings.

```bash
helm repo add intune2snipe https://brngates98.github.io/intune2snipe/
helm repo update
helm search repo intune2snipe --versions
```

Then install a pinned version (create your `Secret` first; see [Helm chart README](../charts/intune2snipe/README.md) for values):

```bash
helm upgrade --install intune2snipe intune2snipe/intune2snipe \
  --version 1.2.3 \
  --namespace intune2snipe --create-namespace
```

### B — Install from a git clone path

Chart path: [`charts/intune2snipe`](../charts/intune2snipe).

```bash
helm upgrade --install intune2snipe ./charts/intune2snipe \
  --namespace intune2snipe --create-namespace \
  --set image.tag=1.2.3
```

### Notes (both paths)

- Create the Kubernetes **Secret** first (name must match **`secrets.existingSecret`**, default `intune2snipe-secrets`).  
- Pin `image.tag` to a **semver** release tag in production, not only `latest`.  
- Full values: [Helm chart README](../charts/intune2snipe/README.md)  

See also [Releases & images](releases-and-images.md).

---

## Option 2 — Plain manifest (`kubectl apply`)

Example: [`k8s/cronjob.yaml`](../k8s/cronjob.yaml).

1. Edit placeholders: Secret `stringData`, CronJob `image`, schedule, resources, optional `args`.  
2. Apply:

   ```bash
   kubectl apply -f k8s/cronjob.yaml
   ```

3. Verify:

   ```bash
   kubectl get cronjob intune2snipe-sync
   kubectl get jobs -l app=intune2snipe-sync
   kubectl logs -l app=intune2snipe-sync --tail=100
   ```

4. Manual one-off job (testing):

   ```bash
   kubectl create job --from=cronjob/intune2snipe-sync intune2snipe-sync-manual-$(date +%s)
   ```

### Private GHCR image

Create an `imagePullSecret` and reference it in the pod spec (Helm: `imagePullSecrets` in `values.yaml`):

```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  --docker-email=<email>
```

```yaml
imagePullSecrets:
  - name: ghcr-secret
```
