"""Run the teacher's E12 check, interrupt its real downstream, then recover."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

LAB = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def http(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as response:
        return json.load(response)


def command(argv, cwd):
    return subprocess.run(argv, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE).stdout


def wait_for(probe, expected, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        observed = probe()
        if observed == expected:
            return
        time.sleep(1)
    raise RuntimeError(f"Expected {expected}, last observation {observed}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api-port", type=int, default=18080)
    parser.add_argument("--prom-port", type=int, default=19090)
    args = parser.parse_args()
    sample, out = args.sample_dir.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    jobs = f"http://127.0.0.1:{args.api_port}/v1/jobs"
    prom = f"http://127.0.0.1:{args.prom_port}/api/v1"
    request = LAB / "request.json"
    timeline = {}

    def mark(key):
        timeline[key] = datetime.now(timezone.utc).isoformat()
        save(out / "timeline.json", timeline)

    def metric(query):
        data = http(prom + "/query?" + urlencode({"query": query}))["data"]["result"]
        return float(data[0]["value"][1]) if data else None

    def target(phase, expected):
        wait_for(lambda: metric('up{job="a03-buildchecker"}'), expected, 60)
        save(out / (phase + "-targets.json"), http(prom + "/targets?state=active"))

    def successful(phase):
        target(phase, 1)
        mark(phase + "_submitted")
        log = command([sys.executable, "scripts/project.py", str(request), "--port",
                       str(args.api_port), "--wait", "600"], sample)
        folder = next(line.split("=", 1)[1] for line in log.splitlines() if line.startswith("EVIDENCE_DIR="))
        dest = out / phase
        shutil.copytree(sample / folder, dest)
        (dest / "client.log").write_text(log)
        repeated = http(jobs, read(dest / "request.json"))
        save(dest / "repeated.json", repeated)
        check = read(dest / "check.json")
        if not check["passed"] or repeated["job_id"] != check["job_id"] or repeated["trace_id"] != check["trace_id"]:
            raise ValueError(f"{phase}: duplicate request changed task identity")
        mark(phase + "_finished")
        print(phase, check["job_id"], "SUCCEEDED", flush=True)

    def compose(*args):
        return command(["docker", "compose", *args], LAB)

    mark("start")
    successful("normal")
    wait_for(lambda: metric('a03_jobs_total{status="SUCCEEDED"}') >= 1, True, 30)
    failed_before = metric('a03_jobs_total{status="FAILED"}')
    mark("stop_requested")
    compose("stop", "buildchecker")
    try:
        target("down", 0)
        mark("down_submitted")
        dest = out / "down"
        dest.mkdir()
        payload = {"input": read(request), "idempotency_key": uuid.uuid4().hex}
        save(dest / "request.json", payload)
        first = http(jobs, payload)
        repeated = http(jobs, payload)
        save(dest / "submitted.json", first)
        save(dest / "repeated.json", repeated)
        if repeated["job_id"] != first["job_id"]:
            raise ValueError("Duplicate fault request dispatched twice")
        url = jobs + "/" + first["job_id"]
        wait_for(lambda: http(url)["status"] in {"SUCCEEDED", "FAILED", "TIMED_OUT"}, True, 600)
        state = http(url)
        result = http(url + "/artifacts")
        save(dest / "status.json", state)
        save(dest / "result.json", result)
        if (state["status"] != "FAILED" or state["error"]["code"] != "DOWNSTREAM_UNAVAILABLE"
                or [s["name"] for s in result["stages"]] != ["draft"]):
            raise ValueError(f"Unexpected failure at {first['job_id']}: {state}")
        mark("down_finished")
        wait_for(lambda: metric('a03_jobs_total{status="FAILED"}'), failed_before + 1, 30)
        print("down", first["job_id"], state["error"]["code"], flush=True)
    finally:
        mark("restart_requested")
        compose("start", "buildchecker")
    compose("up", "-d", "--wait", "--wait-timeout", "60", "buildchecker")
    mark("healthy")
    successful("recovered")
    time.sleep(9)  # Capture two 4-second scrapes after the last job finishes.
    mark("end")
    logs = compose("logs", "--timestamps", "--no-color", "api", "buildchecker")
    (out / "services.log").write_text(logs)
    seen = set()
    for phase in ("normal", "down", "recovered"):
        state = read(out / phase / "status.json")
        job, trace = state["job_id"], state["trace_id"]
        events = []
        for line in logs.splitlines():
            _, _, body = line.partition("|")
            _, _, message = body.strip().partition(" ")
            if message.startswith("{") and job in message:
                events.append(json.loads(message))
        if sum(e["event"] == "job_started" for e in events) != 1 or sum(e["event"] == "job_finished" for e in events) != 1:
            raise ValueError(f"{phase}: expected one execution for the repeated key")
        if not all(e["trace_id"] == trace for e in events) or job in seen:
            raise ValueError(f"{phase}: invalid trace or reused job")
        calls = [e["stage"] for e in events if e["event"] == "checker_call"]
        handled = [e["stage"] for e in events if e["event"] == "check_finished"]
        expected = ["baseline-full", "target-full", "final-full"]
        if calls != (["baseline-full"] if phase == "down" else expected) or handled != ([] if phase == "down" else expected):
            raise ValueError(f"{phase}: unexpected checker activity")
        seen.add(job)
        save(out / phase / "trace.json", sorted(events, key=lambda e: e["timestamp"]))


if __name__ == "__main__":
    main()
