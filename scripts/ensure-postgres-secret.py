import base64
import json
import secrets
import subprocess

command = ["kubectl", "--context", "k3d-kubedeploy", "--namespace", "kubedeploy-demo"]
result = subprocess.run(command + ["get", "secret", "postgres-credentials", "--ignore-not-found", "-o", "json"],
                        text=True, capture_output=True, check=True)
if result.stdout.strip():
    data = json.loads(result.stdout).get("data", {})
    if not all(data.get(key) for key in ("password", "admin-password", "url")):
        raise SystemExit("Existing PostgreSQL Secret is incomplete; it was not changed")
    try:
        for key in ("password", "admin-password", "url"):
            if not base64.b64decode(data[key], validate=True):
                raise ValueError()
    except (ValueError, TypeError):
        raise SystemExit("Existing PostgreSQL Secret has invalid data; it was not changed")
    print("Preserving existing PostgreSQL credentials")
else:
    pvc = subprocess.run(command + ["get", "pvc", "data-postgres-0", "--ignore-not-found", "-o", "name"],
                         text=True, capture_output=True, check=True)
    if pvc.stdout.strip():
        raise SystemExit("PostgreSQL data already exists; restore its credentials before continuing")
    password = secrets.token_hex(32)
    url = f"postgres://kubedeploy:{password}@postgres.kubedeploy-demo.svc.cluster.local:5432/kubedeploy?sslmode=disable"
    secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "postgres-credentials", "namespace": "kubedeploy-demo"},
              "type": "Opaque", "stringData": {"password": password, "admin-password": secrets.token_hex(32), "url": url}}
    subprocess.run(command + ["create", "-f", "-"], input=json.dumps(secret), text=True,
                   stdout=subprocess.DEVNULL, check=True)
    print("Created PostgreSQL credentials")
