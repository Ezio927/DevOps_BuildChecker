"""Serve the existing BuildChecker on the private Compose network."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from time import monotonic

from pipeline import Failure, ROOT, full
from telemetry import Durations, event


PROJECT = {"baseline-full": "base-project", "target-full": "target-project", "final-full": "target-project"}
metrics = Durations("a03_checks", ("SUCCEEDED", "FAILED"))


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "ok", "service": "buildchecker"})
        elif self.path == "/metrics":
            metrics.respond(self)
        else:
            self.reply(404, {"error": "NOT_FOUND"})

    def do_POST(self):
        if self.path != "/v1/full-check":
            return self.reply(404, {"error": "NOT_FOUND"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("Expected up to 4096 bytes")
            body = json.loads(self.rfile.read(size))
            job, trace, stage = body["job_id"], body["trace_id"], body["stage"]
            if not re.fullmatch(r"job-[0-9a-f]{32}", job) or not re.fullmatch(r"trace-[0-9a-f]{32}", trace):
                raise ValueError("Invalid task identifiers")
            project = PROJECT[stage]
        except (KeyError, TypeError, ValueError) as exc:
            return self.reply(400, {"error": str(exc)})
        folder = ROOT / "work/api-jobs" / job / "evidence"
        started = monotonic()
        event("buildchecker", "check_started", job, trace, stage=stage)
        try:
            result = full(folder / project, folder / stage)
            status, code = "SUCCEEDED", 200
        except (Failure, OSError, ValueError) as exc:
            status, code = "FAILED", 422
            result = {"error": str(exc)}
        elapsed = monotonic() - started
        metrics.observe(status, elapsed)
        event("buildchecker", "check_finished", job, trace, stage=stage, status=status,
              duration_ms=round(elapsed * 1000))
        self.reply(code, result)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
