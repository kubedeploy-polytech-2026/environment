import datetime as dt
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "request_deployment", pathlib.Path(__file__).resolve().parents[1] / "scripts/request_deployment.py"
)
request = importlib.util.module_from_spec(spec)
spec.loader.exec_module(request)


class FakeGitHub:
    def __init__(self):
        self.commands = []
        self.posts = []
        self.mutate = lambda metadata: None
        self.draft = False
        self.moved = False
        self.verify = [{"verified": True}]
        self.fail_queue = False
        self.missing_asset = False

    def run(self, *args, body=None):
        self.commands.append(args)
        if args[0] == "attestation":
            self.assert_policy(args)
            return self.verify
        endpoint = args[3]
        if body is not None:
            self.posts.append((endpoint, body))
            if endpoint.endswith("/deployments"):
                return {"id": 42, "sha": body["ref"]}
            if self.fail_queue and body["state"] == "queued":
                raise RuntimeError("status API unavailable")
            return {"id": 100, **body}
        if endpoint.endswith("/commits/main"):
            return {"sha": "a" * 40}
        component = endpoint.split("/")[2]
        tag = "v0.1.0" if component == "backend" else "v0.2.0"
        revision = ("b" if component == "backend" else "c") * 40
        if "/releases/tags/" in endpoint:
            return {"tag_name": tag, "draft": self.draft, "prerelease": False,
                    "assets": [] if self.missing_asset else [{"id": 123, "name": "release.json", "size": 512}]}
        if "/commits/" in endpoint:
            return {"sha": "d" * 40 if self.moved else revision}
        metadata = {"schema_version": "1.0.0", "repository": f"{request.ORG}/{component}",
                    "tag": tag, "revision": revision, "image": f"ghcr.io/{request.ORG}/{component}",
                    "digest": "sha256:" + "e" * 64, "platforms": ["linux/amd64", "linux/arm64"]}
        self.mutate(metadata)
        return metadata

    def assert_policy(self, args):
        for flag in ("--repo", "--source-digest", "--source-ref", "--signer-workflow", "--deny-self-hosted-runners"):
            if flag not in args:
                raise AssertionError(f"Missing provenance policy {flag}")
        repo = args[args.index("--repo") + 1]
        if args[args.index("--signer-workflow") + 1] != f"{repo}/.github/workflows/release.yml":
            raise AssertionError("Wrong signer workflow")


class RequestTests(unittest.TestCase):
    def test_prepare_only_reads_then_create_queues(self):
        fake = FakeGitHub()
        with patch.object(request, "run", side_effect=fake.run):
            body = request.prepare("v0.1.0", "v0.2.0")
            self.assertEqual(fake.posts, [])
            self.assertEqual(body["ref"], "a" * 40)
            self.assertEqual(body["ref"], body["payload"]["environment_revision"])
            self.assertEqual(body["payload"]["backend"]["revision"], "b" * 40)
            self.assertEqual(body["payload"]["frontend"]["revision"], "c" * 40)
            self.assertEqual(body["required_contexts"], [])
            self.assertFalse(body["auto_merge"])
            self.assertFalse(body["production_environment"])
            expires = dt.datetime.fromisoformat(body["payload"]["expires_at"].replace("Z", "+00:00"))
            self.assertTrue(dt.timedelta(minutes=59) < expires - dt.datetime.now(dt.timezone.utc) <= dt.timedelta(hours=1))
            result = request.create(body)
        self.assertEqual(result["deployment_id"], 42)
        self.assertEqual(result["state"], "queued")
        self.assertEqual(len(fake.posts), 2)
        self.assertEqual(fake.posts[-1][1]["state"], "queued")
        self.assertFalse(fake.posts[-1][1]["auto_inactive"])

    def test_invalid_tags_never_contact_github(self):
        for tag in ("latest", "v01.2.3", "v1.2.3-rc1", "v1.2.3/../../main", "$(printenv)"):
            with self.subTest(tag=tag), patch.object(request, "run") as run:
                with self.assertRaises(ValueError):
                    request.prepare(tag, "v0.2.0")
                run.assert_not_called()

    def test_untrusted_release_never_creates_deployment(self):
        for key, value in (("repository", "attacker/backend"), ("image", "ghcr.io/attacker/backend"),
                           ("revision", None), ("digest", "sha256:abc"), ("tag", "v0.3.0"),
                           ("platforms", ["linux/amd64"]), ("extra", True)):
            with self.subTest(key=key):
                fake = FakeGitHub()
                fake.mutate = lambda metadata: metadata.update({key: value})
                with patch.object(request, "run", side_effect=fake.run), self.assertRaises(ValueError):
                    request.prepare("v0.1.0", "v0.2.0")
                self.assertEqual(fake.posts, [])

    def test_draft_moved_tag_missing_asset_and_empty_provenance(self):
        for key, value in (("draft", True), ("moved", True), ("missing_asset", True), ("verify", []), ("verify", [None])):
            with self.subTest(key=key, value=value):
                fake = FakeGitHub()
                setattr(fake, key, value)
                with patch.object(request, "run", side_effect=fake.run), self.assertRaises(ValueError):
                    request.prepare("v0.1.0", "v0.2.0")
                self.assertEqual(fake.posts, [])

    def test_queue_failure_is_reported_without_success(self):
        fake = FakeGitHub()
        fake.fail_queue = True
        with patch.object(request, "run", side_effect=fake.run):
            body = request.prepare("v0.1.0", "v0.2.0")
            with self.assertRaises(RuntimeError):
                request.create(body)
        self.assertEqual([body["state"] for _, body in fake.posts[1:]], ["queued", "error"])

    def test_api_failure_never_creates_deployment(self):
        with patch.object(request, "run", side_effect=RuntimeError("offline")) as run:
            with self.assertRaises(RuntimeError):
                request.prepare("v0.1.0", "v0.2.0")
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
