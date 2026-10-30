#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${BACKEND_IMAGE:?Set BACKEND_IMAGE to an explicitly tagged image or sha256 digest}"
: "${FRONTEND_IMAGE:?Set FRONTEND_IMAGE to an explicitly tagged image or sha256 digest}"
: "${SCORE_K8S:=score-k8s}"
for image_variable in BACKEND_IMAGE FRONTEND_IMAGE; do
  image="${!image_variable}"
  if [[ "$image" == *@* ]]; then
    [[ "$image" =~ ^[^[:space:]@]+@sha256:[a-f0-9]{64}$ ]] || {
      echo "$image_variable must use a complete sha256 digest" >&2; exit 1;
    }
  else
    image_name="${image##*/}"
    [[ "$image_name" =~ ^[^[:space:]:]+:[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$ && "${image_name##*:}" != latest ]] || {
      echo "$image_variable must include an explicit tag other than latest" >&2; exit 1;
    }
  fi
done
"$SCORE_K8S" check-version '=0.19.0' >/dev/null
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
cd "$work_dir"
"$SCORE_K8S" --quiet init --no-sample --no-default-provisioners \
  --provisioners "$project_root/score/route.provisioners.yaml" \
  --provisioners "$project_root/score/postgres.provisioners.yaml" \
  --patch-templates "$project_root/score/security.tpl"
"$SCORE_K8S" --quiet generate "$project_root/score/backend.yaml" \
  --image "$BACKEND_IMAGE" --namespace kubedeploy-demo --output workloads.yaml
"$SCORE_K8S" --quiet generate "$project_root/score/frontend.yaml" \
  --image "$FRONTEND_IMAGE" --namespace kubedeploy-demo --output workloads.yaml
mkdir -p "$project_root/build"
cp workloads.yaml "$project_root/build/workloads.yaml"
echo 'Rendered build/workloads.yaml'
