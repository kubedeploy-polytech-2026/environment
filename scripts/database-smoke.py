import hashlib
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
KUBE = ["kubectl", "--context", "k3d-kubedeploy", "--namespace", "kubedeploy-demo"]


def identity():
    data = json.loads(subprocess.check_output(KUBE + ["get", "secret", "postgres-credentials", "-o", "json"]))["data"]
    pvc = json.loads(subprocess.check_output(KUBE + ["get", "pvc", "data-postgres-0", "-o", "json"]))
    return pvc["metadata"]["uid"], hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def sql(statement):
    command = KUBE + ["exec", "-i", "statefulset/postgres", "--", "sh", "-ec",
                      'export PGPASSWORD="$PG_APP_PASSWORD"; exec psql --no-password -h 127.0.0.1 -U kubedeploy -d kubedeploy -v ON_ERROR_STOP=1 -At']
    return subprocess.run(command, input=statement, text=True, capture_output=True, check=True).stdout.strip()


before = identity()
probe = uuid.uuid4().hex
sql("CREATE TABLE IF NOT EXISTS app.kubedeploy_smoke (id integer PRIMARY KEY, value text NOT NULL);\n"
    f"INSERT INTO app.kubedeploy_smoke VALUES (1, '{probe}') ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value;\n")
print("Inserted PostgreSQL persistence probe", flush=True)
subprocess.run(KUBE + ["delete", "pod", "postgres-0", "--wait=true"], check=True)
subprocess.run(KUBE + ["wait", "--for=create", "pod/postgres-0", "--timeout=120s"], check=True)
subprocess.run(KUBE + ["wait", "--for=condition=Ready", "pod/postgres-0", "--timeout=180s"], check=True)
subprocess.run(["bash", str(ROOT / "scripts/database-up.sh")], check=True)
if identity() != before or sql("SELECT value FROM app.kubedeploy_smoke WHERE id = 1;\n") != probe:
    raise SystemExit("PostgreSQL persistence check failed")
print("PostgreSQL persistence passed: Pod restart, Helm upgrade, same PVC and credentials")
