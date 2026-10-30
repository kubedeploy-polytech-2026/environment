import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RENDER_IMAGE = "ghcr.io/kubedeploy-polytech-2026/deploy-controller@sha256:e81676409e4f9d7c556b946806e39551672b482f5b5b938495fe7fa2c8c02004"


class BackendDatabaseTests(unittest.TestCase):
    def test_score_renders_secret_reference_without_database_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "config.json").write_text('{"auths":{}}')
            command = ["docker", "run", "--rm", "--read-only", "--network", "none", "--tmpfs", "/tmp:rw,size=128m",
                       "--entrypoint", "bash", "-v", f"{ROOT / 'score'}:/source/score:ro",
                       "-v", f"{ROOT / 'scripts/render.sh'}:/source/render.sh:ro",
                       "--env", "BACKEND_IMAGE=ghcr.io/example/backend@sha256:" + "a" * 64,
                       "--env", "FRONTEND_IMAGE=ghcr.io/example/frontend@sha256:" + "b" * 64,
                       RENDER_IMAGE, "-ceu", """
mkdir -p /tmp/project/scripts
cp -R /source/score /tmp/project/score
cp /source/render.sh /tmp/project/scripts/render.sh
cd /tmp/project
bash scripts/render.sh >/dev/null
KUBECONFIG=/dev/null kubectl label --local -f build/workloads.yaml test.kubedeploy.io/rendered=true -o json
"""]
            result = subprocess.run(command, env={**os.environ, "DOCKER_CONFIG": temp},
                                    text=True, capture_output=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("postgres://", result.stdout)
            raw = result.stdout.strip()
            objects = []
            decoder = json.JSONDecoder()
            while raw:
                value, end = decoder.raw_decode(raw)
                objects.extend(value["items"] if value.get("kind") == "List" else [value])
                raw = raw[end:].strip()
            self.assertEqual({obj["kind"] for obj in objects}, {"Deployment", "Service", "HTTPRoute"})
            backend = next(obj for obj in objects if obj["kind"] == "Deployment" and obj["metadata"]["name"] == "backend")
            api = next(c for c in backend["spec"]["template"]["spec"]["containers"] if c["name"] == "api")
            database = next(item for item in api["env"] if item["name"] == "DATABASE_URL")
            self.assertEqual(database, {"name": "DATABASE_URL", "valueFrom": {"secretKeyRef": {"name": "postgres-credentials", "key": "url"}}})
            self.assertEqual(api["readinessProbe"]["httpGet"]["path"], "/readyz")
            self.assertEqual(api["livenessProbe"]["httpGet"]["path"], "/health")


if __name__ == "__main__":
    unittest.main()
