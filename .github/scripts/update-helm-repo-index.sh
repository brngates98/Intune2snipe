#!/usr/bin/env bash
# Build index.yaml for GitHub Pages Helm repository. Chart packages stay on GitHub Releases;
# index.yaml references their download URLs.
set -euo pipefail

TAG="${TAG:?Set TAG to the release tag (e.g. v1.0.0)}"
OWNER="${GITHUB_REPOSITORY_OWNER:?}"
REPO="${GITHUB_REPOSITORY#*/}"
VER="${TAG#v}"
CHART_FILE="intune2snipe-${VER}.tgz"
BASE_URL="https://github.com/${OWNER}/${REPO}/releases/download/${TAG}/"
OUT_DIR="${GITHUB_WORKSPACE:?}/helm-chart-repo"

# Previous index (for merge): live site after last deploy, or override for tests
PREVIOUS_INDEX_URL="${PREVIOUS_INDEX_URL:-https://${OWNER}.github.io/${REPO}/index.yaml}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

MERGE_FILE=""
if curl -fsSL -o "${TMP}/previous-index.yaml" "$PREVIOUS_INDEX_URL" 2>/dev/null && [[ -s "${TMP}/previous-index.yaml" ]]; then
  MERGE_FILE="${TMP}/previous-index.yaml"
  echo "Merging with existing index from ${PREVIOUS_INDEX_URL}"
fi

WORKDIR="${TMP}/charts"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Prefer a local .tgz (e.g. CI artifact from the same workflow) to avoid races where
# GitHub Releases download URLs are not ready immediately after the release job finishes.
if [[ -n "${CHART_LOCAL_DIR:-}" ]] && [[ -d "$CHART_LOCAL_DIR" ]]; then
  found=$(find "$CHART_LOCAL_DIR" -maxdepth 1 -name 'intune2snipe-*.tgz' -print -quit)
  if [[ -n "$found" && -f "$found" ]]; then
    cp "$found" "$CHART_FILE"
    echo "Using chart package from CHART_LOCAL_DIR: $found"
  fi
fi

if [[ ! -f "$CHART_FILE" ]]; then
  echo "Downloading ${CHART_FILE} from release ${TAG}..."
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsSL -o "$CHART_FILE" "${BASE_URL}${CHART_FILE}"; then
      break
    fi
    echo "Retry $i..."
    sleep 5
  done
fi

if [[ ! -f "$CHART_FILE" ]]; then
  echo "Failed to obtain chart package (artifact or ${BASE_URL}${CHART_FILE})"
  exit 1
fi

if [[ -n "$MERGE_FILE" ]]; then
  helm repo index . --url "${BASE_URL}" --merge "$MERGE_FILE"
else
  echo "Creating initial Helm repo index (no previous index at ${PREVIOUS_INDEX_URL})"
  helm repo index . --url "${BASE_URL}"
fi

mkdir -p "$OUT_DIR"
cp index.yaml "$OUT_DIR/index.yaml"

cat >"$OUT_DIR/README.md" <<EOF
# Intune2snipe Helm chart repository

This site is **published by GitHub Actions** when a release is published. Do not edit by hand.

Add the repository:

\`\`\`bash
helm repo add intune2snipe https://${OWNER}.github.io/${REPO}/
helm repo update
helm search repo intune2snipe --versions
\`\`\`

Install (pick a version from \`helm search\`):

\`\`\`bash
helm upgrade --install intune2snipe intune2snipe/intune2snipe --version ${VER} \\
  --namespace intune2snipe --create-namespace
\`\`\`

See [Kubernetes deployment](https://github.com/${OWNER}/${REPO}/blob/main/docs/deployment-kubernetes.md).
EOF

echo "Wrote ${OUT_DIR}/index.yaml"
