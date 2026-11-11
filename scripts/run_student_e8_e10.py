"""241880444: log three personal EChecker experiments on the course host."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = (root / args.out).resolve()
    if not output.is_relative_to(root / "work") or output == root / "work":
        parser.error("Keep evidence below work/")
    if any((output / name).exists() for name in ("e8", "e9", "e10", "summary.json", "commands")):
        parser.error("Use a fresh experiment output; prebuilt environment logs may be retained")
    output.mkdir(parents=True, exist_ok=True)
    sid = subprocess.check_output(["git", "config", "user.name"], cwd=root, text=True).strip()
    if sid != "241880444":
        parser.error("This is the personal experiment runner for 241880444")
    image = "course-e8e10:" + sid
    meta = {"student_id": sid, "status": "RUNNING", "provenance": "EXECUTION",
            "time_utc": datetime.now(timezone.utc).isoformat(), "commands": []}
    meta["source_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    meta["source_status"] = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
    if meta["source_status"]:
        raise ValueError("Formal experiment source must be committed and clean")

    def logged(name, command, timeout=1200):
        folder = output / "commands" / name
        folder.mkdir(parents=True)
        entry = {"argv": command, "cwd": str(root), "time_utc": datetime.now(timezone.utc).isoformat()}
        start = time.monotonic()
        with (folder / "stdout.log").open("w") as out, (folder / "stderr.log").open("w") as err:
            code = subprocess.run(command, cwd=root, stdout=out, stderr=err, timeout=timeout).returncode
        entry.update(exit_code=code, elapsed_s=time.monotonic()-start, passed=code == 0)
        (folder / "command.json").write_text(json.dumps(entry, indent=2)+"\n")
        meta["commands"].append(entry)
        print(name, "exit", code, flush=True)
        for file in ("stdout.log", "stderr.log"):
            print("\n".join((folder / file).read_text(errors="replace").splitlines()[-12:]), flush=True)
        if code:
            raise ValueError(name+" failed; inspect saved original logs")
        return folder

    try:
        logged("doctor", [sys.executable, "scripts/doctor.py", "--out", str(output / "env.json")])
        inspect = logged("environment-image", ["docker", "image", "inspect", image])
        image_id = json.loads((inspect / "stdout.log").read_text())[0]["Id"]
        meta["image_id"] = image_id
        meta["environment_dockerfile_sha256"] = hashlib.sha256((root / "labs/e8e10/environment/services/buildchecker/Dockerfile").read_bytes()).hexdigest()
        command = ["docker", "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "1g",
                   "--pids-limit", "256", "--security-opt", "no-new-privileges:true", "--cap-add", "SYS_PTRACE",
                   "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", "-v", str(root)+":/course", "-w", "/course", image]
        units = logged("unit-tests", command+["python3", "-m", "unittest", "discover", "-s", "labs/e8e10", "-p", "test_profile.py", "-v"])
        text = (units / "stderr.log").read_text()
        meta["unit_tests"] = int(re.search(r"Ran (\d+) tests", text).group(1))
        for stage in ("e8", "e9", "e10"):
            destination = "/course/" + (output / stage).relative_to(root).as_posix()
            logged(stage, command+["python3", "labs/e8e10/student_241880444.py", stage,
                                   "--out", destination, "--image-id", image_id])
            result = json.loads((output / stage / "summary.json").read_text())
            assert result["status"] == "PASSED" and result["source_sha"] == meta["source_sha"]
        logged("scan", [sys.executable, "scripts/secret_scan.py", ".", "--history", "--image", image])
        meta.update(status="PASSED", standard_measurement_pairs=30, extension_measurement_pairs=5)
    except Exception as exc:
        meta.update(status="FAILED", error=type(exc).__name__+": "+str(exc))
        raise
    finally:
        meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "summary.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2)+"\n")
        print("EVIDENCE_DIR="+str(output), flush=True)


if __name__ == "__main__":
    main()
