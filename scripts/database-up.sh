#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context=k3d-kubedeploy
kubectl --context "$context" apply --server-side --field-manager=kubedeploy-score -f "$project_root/kubernetes/namespace.yaml"
helm lint "$project_root/database/postgres"
python3 "$project_root/scripts/ensure-postgres-secret.py"
helm --kube-context "$context" upgrade --install postgres "$project_root/database/postgres" \
  --namespace kubedeploy-demo --wait --atomic --cleanup-on-fail --timeout 5m
helm --kube-context "$context" test postgres --namespace kubedeploy-demo --timeout 2m
