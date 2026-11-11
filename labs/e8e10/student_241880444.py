"""241880444 personal E8-E10 experiments with independent edge oracles."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import time

import lab

BASE_ACTUAL = {"main.o": ["config.h", "main.c"], "helper.o": ["helper.c"]}
BASE_DECLARED = {"main.o": ["main.c", "unused.h"], "helper.o": ["helper.c"]}
BASE_ERRORS = {("MISSING", "main.o", "config.h"), ("REDUNDANT", "main.o", "unused.h")}
TARGETS = {"main.o", "helper.o"}


def errors(report):
    rows = [(f["type"], f["target"], f["dependency"]) for f in report["findings"]]
    assert len(rows) == len(set(rows)), "Duplicate findings"
    return set(rows)


def expect(report, actual, declared, findings):
    assert report["actual"] == actual, (report["actual"], actual)
    assert report["declared"] == declared, (report["declared"], declared)
    assert errors(report) == findings, (errors(report), findings)


def dynamic_check(project, output, actual, findings):
    lab.buildchecker(project, output)
    report = json.loads((output / "findings.json").read_text())
    projected = {tuple(f[k] for k in ("type", "target", "dependency"))
                 for f in report["findings"] if f["target"] in TARGETS}
    assert projected == findings
    edges = json.loads((output / "actual-graph.json").read_text())
    observed = {t: sorted({e["dependency"] for e in edges if e["target"] == t}) for t in actual}
    assert observed == actual


def observe(folder, name, project, previous, actual, declared, findings, dynamic=False):
    incremental = lab.scan(project, previous)
    full = lab.scan(project)
    expect(incremental, actual, declared, findings)
    expect(full, actual, declared, findings)
    for field in ("actual", "declared", "findings"):
        assert incremental[field] == full[field]
    lab.save(folder / (name + ".json"), incremental)
    lab.save(folder / (name + "-full.json"), full)
    lab.save(folder / (name + "-oracle.json"), {
        "provenance": "MANUAL_241880444", "actual": actual, "declared": declared,
        "findings": sorted(findings), "scope": "main.o/helper.o project dependencies"})
    if dynamic:
        dynamic_check(project, folder / (name + "-dynamic"), actual, findings)
    return incremental


def history(project, output):
    lab.run(["git", "bundle", "create", str(output.resolve()), "--all"], project)
    lab.run(["git", "bundle", "verify", str(output.resolve())], project)


def declaration_only_case(folder, dynamic=False):
    project = folder / "project"
    lab.fixture(project)
    baseline = observe(folder, "baseline", project, None, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS, dynamic)
    makefile = project / "Makefile"
    makefile.write_text(makefile.read_text().replace("main.c unused.h", "main.c unused.h extra.h"))
    lab.commit(project, "Declare existing unused extra.h without changing reads")
    declared = {"main.o": ["extra.h", "main.c", "unused.h"], "helper.o": ["helper.c"]}
    extra = ("REDUNDANT", "main.o", "extra.h")
    added = observe(folder, "extra-declaration", project, baseline, BASE_ACTUAL, declared, BASE_ERRORS | {extra}, dynamic)
    assert added["key"] == baseline["key"]
    assert set(added["reused"]) == TARGETS and added["refreshed"] == []
    assert added["added"] == [list(extra)] and added["resolved"] == []
    makefile.write_text(makefile.read_text().replace("main.c unused.h extra.h", "main.c extra.h"))
    lab.commit(project, "Remove the old unused.h declaration only")
    declared = {"main.o": ["extra.h", "main.c"], "helper.o": ["helper.c"]}
    expected = {("MISSING", "main.o", "config.h"), extra}
    removed = observe(folder, "removed-declaration", project, added, BASE_ACTUAL, declared, expected, dynamic)
    assert removed["key"] == added["key"]
    assert set(removed["reused"]) == TARGETS and removed["refreshed"] == []
    assert removed["added"] == []
    assert removed["resolved"] == [["REDUNDANT", "main.o", "unused.h"]]
    history(project, folder / "project-history.bundle")
    return {"passed": True, "case": "declaration_only_recomputes_errors_while_reusing_actual_graph"}


def helper_lifecycle_case(folder, dynamic=False):
    project = folder / "project"
    lab.fixture(project)
    baseline = observe(folder, "C0", project, None, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS, dynamic)
    source = project / "helper.c"
    original = source.read_text()
    source.write_text('#include "extra.h"\n' + original)
    lab.commit(project, "C1 helper includes an undeclared existing header")
    actual = {"main.o": ["config.h", "main.c"], "helper.o": ["extra.h", "helper.c"]}
    missing = ("MISSING", "helper.o", "extra.h")
    one = observe(folder, "C1", project, baseline, actual, BASE_DECLARED, BASE_ERRORS | {missing}, dynamic)
    assert one["added"] == [list(missing)] and one["resolved"] == []
    assert set(one["refreshed"]) == TARGETS
    makefile = project / "Makefile"
    makefile.write_text(makefile.read_text().replace("helper.o: helper.c", "helper.o: helper.c extra.h"))
    lab.commit(project, "C2 fix helper dependency declaration only")
    declared = {"main.o": ["main.c", "unused.h"], "helper.o": ["extra.h", "helper.c"]}
    two = observe(folder, "C2", project, one, actual, declared, BASE_ERRORS, dynamic)
    assert set(two["reused"]) == TARGETS and two["refreshed"] == []
    assert two["added"] == [] and two["resolved"] == [list(missing)]
    source.write_text(original)
    lab.commit(project, "C3 remove include and retain its declaration")
    redundant = ("REDUNDANT", "helper.o", "extra.h")
    three = observe(folder, "C3", project, two, BASE_ACTUAL, declared, BASE_ERRORS | {redundant}, dynamic)
    assert three["added"] == [list(redundant)] and three["resolved"] == []
    assert set(three["refreshed"]) == TARGETS
    history(project, folder / "project-history.bundle")
    return {"passed": True, "case": "helper_header_missing_then_correct_then_redundant"}


def correct_dependency_case(folder, dynamic=False):
    project = folder / "project"
    lab.fixture(project)
    baseline = observe(folder, "baseline", project, None, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS, dynamic)
    source = project / "helper.c"
    source.write_text('#include "extra.h"\n' + source.read_text())
    makefile = project / "Makefile"
    makefile.write_text(makefile.read_text().replace("helper.o: helper.c", "helper.o: helper.c extra.h"))
    lab.commit(project, "Add helper include together with its correct declaration")
    actual = {"main.o": ["config.h", "main.c"], "helper.o": ["extra.h", "helper.c"]}
    declared = {"main.o": ["main.c", "unused.h"], "helper.o": ["extra.h", "helper.c"]}
    changed = observe(folder, "correct-addition", project, baseline, actual, declared, BASE_ERRORS, dynamic)
    assert changed["actual"] != baseline["actual"]
    assert changed["findings"] == baseline["findings"]
    assert changed["added"] == changed["resolved"] == []
    assert set(changed["refreshed"]) == TARGETS and changed["reused"] == []
    history(project, folder / "project-history.bundle")
    return project, baseline, actual, declared


def csv_rows(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def performance_summary(rows):
    result = []
    for case in dict.fromkeys(r["case"] for r in rows):
        selected = [r for r in rows if r["case"] == case]
        inc = [r["incremental_s"] for r in selected]
        full = [r["full_s"] for r in selected]
        result.append({"case": case, "n": len(selected),
                       "incremental_median_ms": statistics.median(inc)*1000,
                       "full_median_ms": statistics.median(full)*1000,
                       "full_over_incremental": statistics.median(full)/statistics.median(inc),
                       "incremental_min_ms": min(inc)*1000, "incremental_max_ms": max(inc)*1000,
                       "incremental_stdev_ms": statistics.stdev(inc)*1000,
                       "full_min_ms": min(full)*1000, "full_max_ms": max(full)*1000,
                       "full_stdev_ms": statistics.stdev(full)*1000})
    return result


def standard_e9(folder):
    folder.mkdir()
    project = folder / "project"
    lab.fixture(project)
    previous = observe(folder, "C0", project, None, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS, True)
    (folder / "C0-build.log").write_text(lab.run(["make", "app"], project))
    assert lab.run(["./app"], project).strip() == "1"
    time.sleep(1.05)
    source = project / "main.c"
    source.write_text(source.read_text().replace("VALUE+helper()", "VALUE+helper()+0"))
    lab.commit(project, "C1 ordinary expression change")
    (folder / "C1-build.log").write_text(lab.run(["make", "app"], project))
    one = observe(folder, "C1", project, previous, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS)
    assert set(one["reused"]) == TARGETS
    time.sleep(1.05)
    source.write_text('#include "extra.h"\n'+source.read_text())
    lab.commit(project, "C2 new include without declaration")
    (folder / "C2-build.log").write_text(lab.run(["make", "app"], project))
    actual = {"main.o": ["config.h", "extra.h", "main.c"], "helper.o": ["helper.c"]}
    two = observe(folder, "C2", project, one, actual, BASE_DECLARED, BASE_ERRORS | {("MISSING", "main.o", "extra.h")})
    assert set(two["refreshed"]) == TARGETS
    makefile = project / "Makefile"
    makefile.write_text(makefile.read_text().replace("main.c unused.h", "main.c unused.h config.h extra.h"))
    lab.commit(project, "C3 repair declarations only")
    declared = {"main.o": ["config.h", "extra.h", "main.c", "unused.h"], "helper.o": ["helper.c"]}
    three = observe(folder, "C3", project, two, actual, declared, {("REDUNDANT", "main.o", "unused.h")}, True)
    assert set(three["reused"]) == TARGETS
    assert three["resolved"] == [["MISSING", "main.o", "config.h"], ["MISSING", "main.o", "extra.h"]]
    for name in ("C1", "C2"):
        text = (folder / (name+"-build.log")).read_text()
        assert "-c main.c" in text and "-c helper.c" not in text
    history(project, folder / "project-history.bundle")


def standard_e10(folder):
    folder.mkdir()
    project = folder / "project"
    lab.fixture(project)
    previous = observe(folder, "baseline", project, None, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS, True)
    rows = []
    actual, declared, findings = BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS
    for case in ("unchanged", "body", "include", "declaration", "flags", "header"):
        if case == "body": (project / "helper.c").write_text("int helper(void){return 0+0;}\n")
        if case == "include":
            p = project / "main.c"; p.write_text('#include "extra.h"\n'+p.read_text())
            actual = {"main.o": ["config.h", "extra.h", "main.c"], "helper.o": ["helper.c"]}
            findings = BASE_ERRORS | {("MISSING", "main.o", "extra.h")}
        if case == "declaration":
            p = project / "Makefile"; p.write_text(p.read_text().replace("main.c unused.h", "main.c unused.h config.h extra.h"))
            declared = {"main.o": ["config.h", "extra.h", "main.c", "unused.h"], "helper.o": ["helper.c"]}
            findings = {("REDUNDANT", "main.o", "unused.h")}
        if case == "flags":
            p = project / "Makefile"; p.write_text(p.read_text().replace("-O0", "-O1"))
        if case == "header": (project / "config.h").write_text('#include "extra.h"\n#define VALUE 1\n')
        if case != "unchanged": lab.commit(project, case)
        for repeat in range(1, 6):
            incremental = observe(folder, f"{case}-{repeat}", project, previous, actual, declared, findings)
            full = json.loads((folder / f"{case}-{repeat}-full.json").read_text())
            reused = case in ("unchanged", "body", "declaration")
            assert set(incremental["reused"]) == (TARGETS if reused else set())
            rows.append({"case": case, "repeat": repeat, "equal": True, "independent_expected": True,
                         "incremental_s": incremental["elapsed_s"], "full_s": full["elapsed_s"],
                         "reused": len(incremental["reused"]), "refreshed": len(incremental["refreshed"])})
        previous = incremental
    dynamic_check(project, folder / "final-buildchecker", actual, findings)
    history(project, folder / "project-history.bundle")
    csv_rows(folder / "results.csv", rows)
    csv_rows(folder / "performance-summary.csv", performance_summary(rows))
    lab.save(folder / "gate.json", {"passed": True, "rows": len(rows), "all_pairs_saved": True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["e8", "e9", "e10"])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = (root / args.out).resolve()
    if not out.is_relative_to(root / "work") or out == root / "work" or out.exists():
        parser.error("Use a fresh directory below work/")
    out.mkdir(parents=True)
    summary = {"student_id": "241880444", "stage": args.stage, "status": "RUNNING",
               "provenance": "EXECUTION", "time_utc": datetime.now(timezone.utc).isoformat(),
               "source_sha": lab.run(["git", "rev-parse", "HEAD"], root).strip(),
               "source_status": lab.run(["git", "status", "--porcelain"], root).strip(),
               "image_id": args.image_id, "reference": "course lab.py", "personal_code": __file__}
    try:
        assert not summary["source_status"]
        if args.stage == "e8":
            lab.demo("e8", out / "standard", "A")
            baseline = json.loads((out / "standard/baseline.json").read_text())
            unchanged = json.loads((out / "standard/incremental.json").read_text())
            expect(baseline, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS)
            expect(unchanged, BASE_ACTUAL, BASE_DECLARED, BASE_ERRORS)
            assert set(unchanged["reused"]) == TARGETS and unchanged["refreshed"] == []
            history(out / "standard/project", out / "standard/project-history.bundle")
            extension = out / "extension"; extension.mkdir()
            summary["extension"] = declaration_only_case(extension, True)
        elif args.stage == "e9":
            standard_e9(out / "standard")
            extension = out / "extension"; extension.mkdir()
            summary["extension"] = helper_lifecycle_case(extension, True)
        else:
            standard_e10(out / "standard")
            extension = out / "extension"; extension.mkdir()
            project, baseline, actual, declared = correct_dependency_case(extension, True)
            rows = []
            for repeat in range(1, 6):
                inc = observe(extension, f"measurement-{repeat}", project, baseline, actual, declared, BASE_ERRORS)
                full = json.loads((extension / f"measurement-{repeat}-full.json").read_text())
                assert inc["added"] == inc["resolved"] == []
                assert set(inc["refreshed"]) == TARGETS
                rows.append({"case": "correct-helper-dependency", "repeat": repeat, "equal": True,
                             "incremental_s": inc["elapsed_s"], "full_s": full["elapsed_s"]})
            csv_rows(extension / "results.csv", rows)
            csv_rows(extension / "performance-summary.csv", performance_summary(rows))
            summary["extension"] = {"passed": True, "case": "actual_graph_changes_with_unchanged_error_set", "measurement_pairs": 5}
        summary["status"] = "PASSED"
    except Exception as exc:
        summary.update(status="FAILED", error=type(exc).__name__+": "+str(exc))
        raise
    finally:
        lab.save(out / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
