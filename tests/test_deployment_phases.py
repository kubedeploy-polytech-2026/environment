import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.log = self.folder / "calls.jsonl"
        kubectl = self.folder / "kubectl"
        kubectl.write_text("""#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ['TEST_CALLS'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if 'rollout' in sys.argv and 'deployment/backend' in sys.argv:
    time.sleep(float(os.environ.get('TEST_WAIT', '0')))
""")
        kubectl.chmod(0o700)
        self.env = {**os.environ, "PATH": f"{self.folder}{os.pathsep}{os.environ['PATH']}",
                    "TEST_CALLS": str(self.log), "BACKEND_IMAGE": "ghcr.io/example/backend@sha256:" + "a" * 64,
                    "FRONTEND_IMAGE": "ghcr.io/example/frontend@sha256:" + "b" * 64}

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def run_script(self, name, **env):
        return subprocess.run(["bash", str(ROOT / "scripts" / name)], env={**self.env, **env},
                              cwd=self.folder, text=True, capture_output=True, timeout=10)

    def test_apply_never_waits_or_smokes(self):
        result = self.run_script("deploy.sh", DEPLOY_PHASE="apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertTrue(any("apply" in call and "--dry-run=server" not in call for call in calls))
        self.assertFalse(any("rollout" in call or "port-forward" in call for call in calls))

    def test_wait_only_observes_with_one_shared_budget(self):
        result = self.run_script("wait.sh", ROLLOUT_TIMEOUT_SECONDS="4", TEST_WAIT="1.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("rollout" in call and "apply" not in call for call in calls))
        seconds = [int(next(arg for arg in call if arg.startswith("--timeout=")).split("=")[1][:-1]) for call in calls]
        self.assertGreater(seconds[0], seconds[1])
        self.assertGreater(seconds[1], 0)

    def test_exhausted_budget_does_not_start_second_wait(self):
        result = self.run_script("wait.sh", ROLLOUT_TIMEOUT_SECONDS="1", TEST_WAIT="1.1")
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(len(self.calls()), 1)

    def test_invalid_timeout_fails_before_mutation(self):
        for value in ("0", "-1", "1s", "01", "3601", "999999999999999999999", "$(printenv)"):
            with self.subTest(value=value):
                result = self.run_script("deploy.sh", ROLLOUT_TIMEOUT_SECONDS=value)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
