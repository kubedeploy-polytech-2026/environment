#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/timeout.sh
validate_rollout_timeout
deadline=$((SECONDS + ROLLOUT_TIMEOUT_SECONDS))
for workload in backend frontend; do
  remaining=$((deadline - SECONDS))
  (( remaining > 0 )) || { echo 'Application rollout deadline exceeded' >&2; exit 124; }
  kubectl --context k3d-kubedeploy --namespace kubedeploy-demo \
    rollout status "deployment/$workload" "--timeout=${remaining}s"
done
