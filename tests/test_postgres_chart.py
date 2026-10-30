from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ChartTests(unittest.TestCase):
    def test_invalid_chart_configuration_is_rejected(self):
        for setting in ("image.tag=latest", "image.tag=LATEST", "image.digest=sha256:invalid",
                        "database.user=postgres", "database.name=bad;name", "resources.limits.memory="):
            with self.subTest(setting=setting):
                result = subprocess.run(["helm", "template", "postgres", str(ROOT / "database/postgres"),
                                         "--set-string", setting], text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("schema", result.stderr)


if __name__ == "__main__":
    unittest.main()
