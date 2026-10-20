#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
: "${BACKEND_IMAGE:?Set BACKEND_IMAGE explicitly}"
: "${FRONTEND_IMAGE:?Set FRONTEND_IMAGE explicitly}"
context=k3d-kubedeploy

# Fail before changing application resources if the shared Gateway is unavailable.
kubectl --context "$context" --namespace kubedeploy-gateway wait \
  --for=condition=Programmed gateway/kubedeploy --timeout=60s

# Local images must already be built; registry images can be pulled by k3d.
for image in "$BACKEND_IMAGE" "$FRONTEND_IMAGE"; do
  if [[ "$image" != *@* ]] && docker image inspect "$image" >/dev/null 2>&1; then
    k3d image import --cluster kubedeploy "$image"
  fi
done
kubectl --context "$context" apply --server-side --field-manager=kubedeploy-score \
  -f kubernetes/namespace.yaml
kubectl --context "$context" apply --server-side --dry-run=server \
  --field-manager=kubedeploy-score -f build/workloads.yaml
kubectl --context "$context" apply --server-side --field-manager=kubedeploy-score \
  -f build/workloads.yaml
kubectl --context "$context" --namespace kubedeploy-demo \
  rollout status deployment/backend --timeout=180s
kubectl --context "$context" --namespace kubedeploy-demo \
  rollout status deployment/frontend --timeout=180s
bash scripts/smoke.sh
