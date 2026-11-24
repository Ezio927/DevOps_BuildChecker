"""Export the live Grafana dashboard and the data behind its exact time window."""
import argparse
import base64
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def fetch(url, headers):
    with urlopen(Request(url, headers=headers), timeout=15) as response:
        return json.load(response)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grafana", required=True, help="Loopback Grafana URL")
    p.add_argument("--uid", required=True, help="Grafana dashboard UID")
    p.add_argument("--start", type=int, required=True, help="UTC Unix seconds")
    p.add_argument("--end", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    basic = base64.b64encode(("admin:" + os.environ["GRAFANA_ADMIN_PASSWORD"]).encode()).decode()
    headers = {"Authorization": "Basic " + basic}
    root = args.grafana.rstrip("/")
    dashboard = fetch(root + "/api/dashboards/uid/" + quote(args.uid), headers)["dashboard"]
    args.out.mkdir(parents=True, exist_ok=False)

    def save(name, obj):
        (args.out / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")

    save("dashboard.json", dashboard)
    result = []
    for panel in dashboard["panels"]:
        uid = panel["datasource"]["uid"]
        for target in panel["targets"]:
            query = {"query": target["expr"], "start": args.start, "end": args.end, "step": 4}
            endpoint = root + "/api/datasources/proxy/uid/" + quote(uid) + "/api/v1/query_range?"
            data = fetch(endpoint + urlencode(query), headers)
            if data["status"] != "success" or not data["data"]["result"]:
                raise ValueError("No observations for " + target["expr"])
            result.append({"panel": panel["title"], **query, "series": data["data"]["result"]})
    save("window.json", {"start": args.start, "end": args.end, "panels": result})


if __name__ == "__main__":
    main()
