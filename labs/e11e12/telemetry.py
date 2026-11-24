"""Business counters and structured events for the E12 HTTP services."""
from datetime import datetime, timezone
import json
from threading import Lock


def event(service, name, job_id, trace_id, **fields):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(), "service": service,
        "event": name, "job_id": job_id, "trace_id": trace_id, **fields,
    }), flush=True)


class Durations:
    def __init__(self, prefix, statuses):
        self.prefix = prefix
        self.counts = dict.fromkeys(statuses, 0)
        self.seconds = 0.0
        self.lock = Lock()

    def observe(self, status, seconds):
        with self.lock:
            self.counts[status] += 1
            self.seconds += seconds

    def respond(self, handler):
        with self.lock:
            lines = [f"# TYPE {self.prefix}_total counter"]
            lines.extend(f'{self.prefix}_total{{status="{status}"}} {count}'
                         for status, count in self.counts.items())
            lines.extend([f"# TYPE {self.prefix}_duration_seconds summary",
                          f"{self.prefix}_duration_seconds_sum {self.seconds:.6f}",
                          f"{self.prefix}_duration_seconds_count {sum(self.counts.values())}"])
        body = ("\n".join(lines) + "\n").encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
