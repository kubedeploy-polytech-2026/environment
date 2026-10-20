#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${BACKEND_IMAGE:?Set BACKEND_IMAGE to an explicitly tagged image or sha256 digest}"
: "${SCORE_K8S:=score-k8s}"
if [[ "$BACKEND_IMAGE" == *@* ]]; then
  [[ "$BACKEND_IMAGE" =~ ^[^[:space:]@]+@sha256:[a-f0-9]{64}$ ]] || {
    echo 'BACKEND_IMAGE must use a complete sha256 digest' >&2; exit 1;
  }
else
  image_name="${BACKEND_IMAGE##*/}"
  [[ "$image_name" =~ ^[^[:space:]:]+:[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$ && "${image_name##*:}" != latest ]] || {
    echo 'BACKEND_IMAGE must include an explicit tag other than latest' >&2; exit 1;
  }
fi
"$SCORE_K8S" check-version '=0.19.0' >/dev/null
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
cd "$work_dir"
"$SCORE_K8S" init --no-sample --no-default-provisioners \
  --provisioners "$project_root/score/route.provisioners.yaml" \
  --patch-templates "$project_root/score/security.tpl" >/dev/null
"$SCORE_K8S" generate "$project_root/score/backend.yaml" \
  --image "$BACKEND_IMAGE" --namespace kubedeploy-demo --output backend.yaml >/dev/null
mkdir -p "$project_root/build"
cp backend.yaml "$project_root/build/backend.yaml"
echo 'Rendered build/backend.yaml'
