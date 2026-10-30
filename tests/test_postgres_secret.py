import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SecretTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.created = self.path / "created.json"
        self.existing = self.path / "existing.json"
        kubectl = self.path / "kubectl"
        kubectl.write_text("""#!/usr/bin/env python3
import os,sys
from pathlib import Path
args=sys.argv[1:]
if 'get' in args and 'secret' in args:
    if os.environ.get('TEST_API_FAILURE')=='1':raise SystemExit(1)
    path=Path(os.environ['TEST_EXISTING'])
    if path.exists():print(path.read_text())
elif 'get' in args and 'pvc' in args:
    if os.environ.get('TEST_PVC')=='1':print('persistentvolumeclaim/data-postgres-0')
elif 'create' in args:
    Path(os.environ['TEST_CREATED']).write_text(sys.stdin.read())
else:raise SystemExit('Unexpected kubectl call')
""")
        kubectl.chmod(0o700)
        self.env = {**os.environ, "PATH": f"{self.path}{os.pathsep}{os.environ['PATH']}",
                    "TEST_EXISTING": str(self.existing), "TEST_CREATED": str(self.created)}

    def run_script(self, **extra):
        return subprocess.run(["python3", str(ROOT / "scripts/ensure-postgres-secret.py")],
                              env={**self.env, **extra}, text=True, capture_output=True, timeout=10)

    def test_initial_credentials_are_separate_and_not_printed(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        secret = json.loads(self.created.read_text())
        data = secret["stringData"]
        self.assertEqual(len(data["password"]), 64)
        self.assertNotEqual(data["password"], data["admin-password"])
        self.assertIn(data["password"], data["url"])
        self.assertNotIn(data["admin-password"], data["url"])
        for value in data.values():
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_existing_credentials_are_preserved(self):
        original = json.dumps({"data": {key: base64.b64encode(b"fixture-only").decode()
                                        for key in ("password", "admin-password", "url")}})
        self.existing.write_text(original)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.created.exists())
        self.assertEqual(self.existing.read_text(), original)

    def test_incomplete_credentials_are_not_replaced(self):
        self.existing.write_text(json.dumps({"data": {"password": "cGFzcw=="}}))
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.created.exists())

    def test_existing_data_prevents_new_credentials(self):
        result = self.run_script(TEST_PVC="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.created.exists())

    def test_api_failure_does_not_create_credentials(self):
        result = self.run_script(TEST_API_FAILURE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.created.exists())


if __name__ == "__main__":
    unittest.main()
