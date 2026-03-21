# Intune2snipe documentation

Sync **Microsoft Intune** managed devices into **Snipe-IT** using a small Python CLI or container.

---

### Start here

| Guide | What you’ll learn |
|--------|-------------------|
| [Getting started](getting-started.md) | Prerequisites, install, first `--dry-run` |
| [Configuration](configuration.md) | Environment variables, Azure app registration, Snipe-IT API token |
| [Usage & CLI](usage-and-cli.md) | Flags, examples, Azure AD group IDs |
| [Deployment — Docker](deployment-docker.md) | Pull/run images, GHCR login, tags |
| [Deployment — Kubernetes](deployment-kubernetes.md) | Helm chart, plain manifest, secrets, CronJob |
| [How it works](how-it-works.md) | Sync pipeline and field mapping |
| [Troubleshooting](troubleshooting.md) | Common errors (Graph, Snipe-IT, Docker/K8s) |
| [Releases & images](releases-and-images.md) | Version tags, `latest` vs pinned, where packages live |

---

### Other references

| Doc | Audience |
|-----|----------|
| [README](../README.md) | Project overview and quick links |
| [Helm chart README](../charts/intune2snipe/README.md) | Chart values and install one-liners |
| [RELEASING.md](../RELEASING.md) | Maintainers: cutting semver releases |

---

### Get help

- [Open an issue](https://github.com/brngates98/intune2snipe/issues) (use a template when possible)
- Check [Troubleshooting](troubleshooting.md) first
