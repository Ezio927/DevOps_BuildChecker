"""241880444: record an actual E5-E7 run without replacing original evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--image", default="course-e5e7:241880444")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = (root / args.out).resolve()
    if not output.is_relative_to(root / "work") or output == root / "work" or output.exists():
        parser.error("Use a new directory under work/")
    output.mkdir(parents=True)
    summary = {"status": "RUNNING", "student_id": "241880444", "provenance": "EXECUTION",
               "started_utc": datetime.now(timezone.utc).isoformat(), "commands": []}
    summary["source_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    summary["working_tree"] = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
    summary["origin"] = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=root, text=True).strip()
    if summary["working_tree"]:
        raise ValueError("Commit experiment source before formal evidence collection")

    def run(name, command, expected=0, timeout=1800):
        folder = output / "commands" / name
        folder.mkdir(parents=True)
        entry = {"name": name, "argv": [str(x) for x in command], "cwd": str(root),
                 "expected_exit_code": expected, "started_utc": datetime.now(timezone.utc).isoformat()}
        start = time.monotonic()
        with (folder / "stdout.log").open("w") as out, (folder / "stderr.log").open("w") as err:
            code = subprocess.run(command, cwd=root, stdout=out, stderr=err, timeout=timeout).returncode
        entry.update(exit_code=code, elapsed_s=time.monotonic()-start, passed=code == expected)
        (folder / "command.json").write_text(json.dumps(entry, indent=2)+"\n")
        summary["commands"].append(entry)
        print(name, "exit", code, "expected", expected, flush=True)
        for filename in ["stdout.log", "stderr.log"]:
            print("\n".join((folder / filename).read_text(errors="replace").splitlines()[-12:]), flush=True)
        if code != expected:
            raise ValueError(name + " did not return the independently expected exit code")
        return folder

    try:
        run("doctor", [sys.executable, "scripts/doctor.py", "--out", str(output / "env.json")])
        base = [sys.executable, "scripts/lab_cloud.py"]
        run("build", base+["build", "--out", str(output / "build"), "--image", args.image, "--build-timeout", "1200"])
        toolchain = run("toolchain", ["docker", "run", "--rm", "--network", "none", args.image, "cat", "/opt/toolchain.lock"])
        shutil.copyfile(toolchain / "stdout.log", output / "toolchain.lock")
        run("e5", base+["e5", "--out", str(output / "e5"), "--image", args.image])
        run("e6-before", base+["e6", "--out", str(output / "e6-before"), "--image", args.image], expected=1)
        run("e6-after", base+["e6", "--fixed", "--out", str(output / "e6-after"), "--image", args.image])
        run("verify-e6", [sys.executable, "scripts/verify_e6_evidence.py", "--before",
                           str(output / "e6-before/evidence/findings.json"), "--after",
                           str(output / "e6-after/evidence/findings.json")])
        run("independent-oracle", [sys.executable, "-m", "unittest", "discover", "-s", "tests/e7", "-v"])
        run("e7", base+["gate", "--out", str(output / "e7"), "--image", args.image])
        run("scan", [sys.executable, "scripts/secret_scan.py", ".", "--history", "--image", args.image])
        gate = json.loads((output / "e7/gate/gate-result.json").read_text())
        assert gate["passed"] and len(gate["cases"]) == 8
        assert (output / "e5/evidence/program-output.txt").read_text().strip() == "1"
        summary.update(status="PASSED", gate_checks=8, e5_output="1", image=args.image)
    except Exception as exc:
        summary.update(status="FAILED", error=type(exc).__name__+": "+str(exc))
        raise
    finally:
        summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
        print("EVIDENCE_DIR="+str(output), flush=True)


if __name__ == "__main__":
    main()
