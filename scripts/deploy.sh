#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
: "${BACKEND_IMAGE:?Set BACKEND_IMAGE explicitly}"
context=k3d-kubedeploy

# Fail before changing application resources if the shared Gateway is unavailable.
kubectl --context "$context" --namespace kubedeploy-gateway wait \
  --for=condition=Programmed gateway/kubedeploy --timeout=60s

# Local images must already be built; registry images can be pulled by k3d.
if [[ "$BACKEND_IMAGE" != *@* ]] && docker image inspect "$BACKEND_IMAGE" >/dev/null 2>&1; then
  k3d image import --cluster kubedeploy "$BACKEND_IMAGE"
fi
kubectl --context "$context" apply --server-side --field-manager=kubedeploy-score \
  -f kubernetes/namespace.yaml
kubectl --context "$context" apply --server-side --dry-run=server \
  --field-manager=kubedeploy-score -f build/backend.yaml
kubectl --context "$context" apply --server-side --field-manager=kubedeploy-score \
  -f build/backend.yaml
kubectl --context "$context" --namespace kubedeploy-demo \
  rollout status deployment/backend --timeout=180s
bash scripts/smoke.sh
