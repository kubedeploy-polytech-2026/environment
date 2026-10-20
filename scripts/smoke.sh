#!/usr/bin/env bash
set -euo pipefail

context=k3d-kubedeploy
namespace=kubedeploy-demo
for route in backend-http frontend-http; do
  for condition in Accepted ResolvedRefs; do
    kubectl --context "$context" --namespace "$namespace" wait \
      "--for=jsonpath={.status.parents[?(@.parentRef.name==\"kubedeploy\")].conditions[?(@.type==\"$condition\")].status}=True" \
      "httproute/$route" --timeout=120s
  done
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
    base_url="http://127.0.0.1:$local_port"
    curl --fail --silent --show-error --max-time 5 --header 'Host: kubedeploy.local' \
      "$base_url/" >"$work_dir/index.html"
    asset="$(python3 - "$work_dir/index.html" <<'PY'
from html.parser import HTMLParser
import sys
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = False
        self.scripts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and attrs.get("id") == "root":
            self.root = True
        if tag == "script" and attrs.get("src", "").startswith("/assets/"):
            self.scripts.append(attrs["src"])
page = Page()
with open(sys.argv[1]) as response:
    page.feed(response.read())
assert page.root and len(page.scripts) == 1, "Expected the frontend HTML and module script"
print(page.scripts[0])
PY
)"
    curl --fail --silent --show-error --max-time 5 --header 'Host: kubedeploy.local' \
      "$base_url$asset" >"$work_dir/asset.js"
    [[ -s "$work_dir/asset.js" ]]
    curl --fail --silent --show-error --max-time 5 --header 'Host: kubedeploy.local' \
      "$base_url/example/nested" >"$work_dir/nested.html"
    cmp "$work_dir/index.html" "$work_dir/nested.html"
    for path in /assets/missing.js /api/missing; do
      status="$(curl --silent --show-error --max-time 5 --output /dev/null \
        --write-out '%{http_code}' --header 'Host: kubedeploy.local' "$base_url$path")"
      [[ "$status" == 404 ]]
    done
    echo 'Gateway smoke passed: UI, JS asset, SPA fallback, API JSON, both HTTPRoutes, missing asset/API and foreign hostname HTTP 404'
    exit 0
  fi
  sleep 1
done
echo 'Applications did not become ready through the shared Gateway' >&2
exit 1
