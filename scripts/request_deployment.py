import argparse
import datetime as dt
import json
import re
import subprocess
import sys

ORG = "kubedeploy-polytech-2026"
REPO = f"{ORG}/environment"
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def run(*args, body=None):
    result = subprocess.run(
        ["gh", *args], input=json.dumps(body) if body is not None else None,
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode:
        raise RuntimeError(f"gh {args[0]} failed")
    return json.loads(result.stdout)


def api(endpoint, body=None, accept=None):
    args = ["api", "--hostname", "github.com", endpoint]
    if body is not None:
        args += ["--method", "POST", "--input", "-"]
    if accept:
        args += ["-H", f"Accept: {accept}"]
    return run(*args, body=body)


def release(component, tag):
    repo = f"{ORG}/{component}"
    published = api(f"repos/{repo}/releases/tags/{tag}")
    if published.get("tag_name") != tag or published.get("draft") or published.get("prerelease"):
        raise ValueError(f"{component}: expected a published stable release")
    assets = [a for a in published.get("assets", []) if a.get("name") == "release.json"]
    if len(assets) != 1 or not isinstance(assets[0].get("id"), int) or assets[0]["id"] <= 0 or not 0 < assets[0].get("size", 0) <= 65536:
        raise ValueError(f"{component}: invalid release.json asset")
    metadata = api(f"repos/{repo}/releases/assets/{assets[0]['id']}", accept="application/octet-stream")
    if not isinstance(metadata, dict):
        raise ValueError(f"{component}: release metadata must be an object")
    if (set(metadata) != {"schema_version", "repository", "tag", "revision", "image", "digest", "platforms"}
            or metadata.get("schema_version") != "1.0.0" or metadata.get("repository") != repo
            or metadata.get("tag") != tag or metadata.get("image") != f"ghcr.io/{repo}"
            or not isinstance(metadata.get("revision"), str) or not SHA.fullmatch(metadata["revision"])
            or not isinstance(metadata.get("digest"), str) or not DIGEST.fullmatch(metadata["digest"])
            or metadata.get("platforms") not in (["linux/amd64", "linux/arm64"], ["linux/arm64", "linux/amd64"])):
        raise ValueError(f"{component}: invalid release metadata")
    if api(f"repos/{repo}/commits/{tag}").get("sha") != metadata["revision"]:
        raise ValueError(f"{component}: release tag moved")
    verified = run(
        "attestation", "verify", f"oci://{metadata['image']}@{metadata['digest']}",
        "--hostname", "github.com", "--repo", repo,
        "--source-digest", metadata["revision"], "--source-ref", f"refs/tags/{tag}",
        "--signer-workflow", f"{repo}/.github/workflows/release.yml",
        "--deny-self-hosted-runners", "--predicate-type", "https://slsa.dev/provenance/v1",
        "--format", "json",
    )
    if not isinstance(verified, list) or not verified or not verified[0]:
        raise ValueError(f"{component}: no verified provenance")
    return {key: metadata[key] for key in ("tag", "revision", "digest")}


def prepare(backend_tag, frontend_tag):
    if not TAG.fullmatch(backend_tag) or not TAG.fullmatch(frontend_tag):
        raise ValueError("Select vMAJOR.MINOR.PATCH release tags")
    revision = api(f"repos/{REPO}/commits/main").get("sha", "")
    if not SHA.fullmatch(revision):
        raise ValueError("Invalid environment main revision")
    backend, frontend = release("backend", backend_tag), release("frontend", frontend_tag)
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    return {
        "ref": revision, "task": "deploy", "auto_merge": False, "required_contexts": [],
        "environment": "local-k3d", "production_environment": False, "transient_environment": False,
        "description": f"backend {backend_tag}, frontend {frontend_tag}",
        "payload": {
            "schema_version": "1.0.0", "environment_revision": revision,
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "backend": backend, "frontend": frontend,
        },
    }


def create(body):
    deployment = api(f"repos/{REPO}/deployments", body=body)
    deployment_id = deployment.get("id")
    if not isinstance(deployment_id, int) or deployment_id <= 0 or deployment.get("sha") != body["ref"]:
        raise ValueError("GitHub did not create the requested deployment")
    endpoint = f"repos/{REPO}/deployments/{deployment_id}/statuses"
    try:
        api(endpoint, body={"state": "queued", "auto_inactive": False, "description": "Waiting for the local deploy controller"})
    except Exception:
        try:
            api(endpoint, body={"state": "error", "auto_inactive": False, "description": "Failed to queue deployment request"})
        except Exception:
            pass
        raise
    return {"deployment_id": deployment_id, "state": "queued", "environment_revision": body["ref"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-tag", required=True)
    parser.add_argument("--frontend-tag", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        body = prepare(args.backend_tag, args.frontend_tag)
        print(json.dumps(body if args.dry_run else create(body), indent=2))
    except (ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
