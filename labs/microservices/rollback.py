"""Check that a valid but incomplete Makefile repair is refused."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e8e10"))
from lab import patch, validate


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def state(repo):
    return {"head": git(repo, "rev-parse", "HEAD"), "status": git(repo, "status", "--porcelain"),
            "makefile_sha256": hashlib.sha256((repo / "Makefile").read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo", type=Path)
    p.add_argument("report", type=Path, help="incremental-check.json from the successful E12 task")
    p.add_argument("out", type=Path)
    args = p.parse_args()
    report = json.loads(args.report.read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    checkout = args.out / "checkout"
    original = state(args.repo)
    subprocess.run(["git", "clone", "--no-hardlinks", str(args.repo), str(checkout)], check=True)
    git(checkout, "checkout", "--detach", report["commit"])
    before = state(checkout)
    missing = [f for f in report["data"]["findings"] if f["type"] == "MISSING"]
    if len(missing) < 2:
        raise ValueError("Choose a target with at least two missing dependencies to test a partial repair")
    diff, _ = patch(checkout, {"commit": report["commit"], "findings": missing[:1]})
    candidate = args.out / "partial.patch"
    candidate.write_text(diff)
    verdict = validate(checkout, candidate, args.out / "validation")
    after = state(checkout)
    original_after = state(args.repo)
    passed = (verdict["checks"].get("patch_applies") and verdict["checks"].get("build") and
              verdict["checks"].get("no_missing") is False and not verdict["accepted"] and
              verdict["rollback"] and verdict["source_unchanged"] and before == after and
              not before["status"] and original == original_after and not original["status"])
    record = {"passed": passed, "job_id": report["job_id"], "trace_id": report["trace_id"],
              "partial_fix": missing[0], "validation": verdict, "checkout_before": before,
              "checkout_after": after, "source_before": original, "source_after": original_after}
    (args.out / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
    if not passed:
        raise SystemExit("Rollback verification failed; see comparison.json")
    print("PASS incomplete patch rejected; source and writable checkout unchanged")


if __name__ == "__main__":
    main()
