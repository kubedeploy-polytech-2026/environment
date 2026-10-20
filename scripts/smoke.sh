#!/usr/bin/env bash
set -euo pipefail

context=k3d-kubedeploy
namespace=kubedeploy-demo
for condition in Accepted ResolvedRefs; do
  kubectl --context "$context" --namespace "$namespace" wait \
    "--for=jsonpath={.status.parents[?(@.parentRef.name==\"kubedeploy\")].conditions[?(@.type==\"$condition\")].status}=True" \
    httproute/backend-http --timeout=120s
done
selector='gateway.envoyproxy.io/owning-gateway-namespace=kubedeploy-gateway,gateway.envoyproxy.io/owning-gateway-name=kubedeploy'
service="$(kubectl --context "$context" --namespace envoy-gateway-system \
  get services --selector "$selector" -o name)"
[[ -n "$service" && "$service" != *$'\n'* ]] || {
  echo 'Expected exactly one Envoy Service for the shared Gateway' >&2; exit 1;
}
work_dir="$(mktemp -d)"
port_forward_pid=''
# shellcheck disable=SC2329 # Invoked by the EXIT trap.
cleanup() {
  result=$?
  if (( result != 0 )); then
    cat "$work_dir/port-forward.log" >&2 || true
    kubectl --context "$context" --namespace "$namespace" get pods,httproute >&2 || true
  fi
  if [[ -n "$port_forward_pid" ]]; then
    kill "$port_forward_pid" 2>/dev/null || true
    wait "$port_forward_pid" 2>/dev/null || true
  fi
  rm -rf "$work_dir"
}
trap cleanup EXIT
kubectl --context "$context" --namespace envoy-gateway-system \
  port-forward "$service" :80 --address=127.0.0.1 >"$work_dir/port-forward.log" 2>&1 &
port_forward_pid=$!

for ((attempt=0; attempt<30; attempt++)); do
  kill -0 "$port_forward_pid" 2>/dev/null || { echo 'Envoy port-forward exited' >&2; exit 1; }
  local_port="$(awk '/^Forwarding from 127.0.0.1:/ {split($3, address, ":"); print address[2]; exit}' "$work_dir/port-forward.log")"
  if [[ -n "$local_port" ]] && curl --fail --silent --max-time 5 \
    --header 'Host: kubedeploy.local' "http://127.0.0.1:$local_port/api/version" >"$work_dir/version.json"; then
    python3 - "$work_dir/version.json" <<'PY'
import json
import sys
with open(sys.argv[1]) as response:
    body = json.load(response)
assert body == {"service": "kubedeploy-backend", "version": "0.1.0"}, body
PY
    status="$(curl --silent --show-error --max-time 5 --output /dev/null \
      --write-out '%{http_code}' --header 'Host: gateway-smoke.invalid' \
      "http://127.0.0.1:$local_port/api/version")"
    [[ "$status" == 404 ]]
    echo 'Backend Gateway smoke passed: /api/version JSON, route Accepted/ResolvedRefs, foreign hostname HTTP 404'
    exit 0
  fi
  sleep 1
done
echo 'Backend did not return /api/version through the shared Gateway' >&2
exit 1
