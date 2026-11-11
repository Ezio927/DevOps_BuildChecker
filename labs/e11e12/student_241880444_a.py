"""Run only E11-A with controlled real Git commits and independent graph checks."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from lab import commit, fixture, run
from pipeline import ROOT, Failure, check_envelope, execute, save

BASE_ACTUAL = {'main.o': ['config.h', 'main.c'], 'helper.o': ['helper.c']}
BASE_DECLARED = {'main.o': ['main.c', 'unused.h'], 'helper.o': ['helper.c']}
BASE_ERRORS = {('MISSING', 'main.o', 'config.h'), ('REDUNDANT', 'main.o', 'unused.h')}


def checks(result, folder, base, target, actual, declared, errors, reused):
    assert result['status'] == 'SUCCEEDED', result
    assert result['base_commit'] == base and result['target_commit'] == target
    assert [s['name'] for s in result['stages']] == ['full-check', 'incremental-check']
    for kind, sha in [('full-check', base), ('incremental-check', target)]:
        report = json.loads((folder / (kind + '.json')).read_text())
        check_envelope(report, sha, kind)
        assert report['job_id'] == result['job_id'] and report['trace_id'] == result['trace_id']
    current = json.loads((folder / 'incremental-report.json').read_text())
    assert current['actual'] == actual and current['declared'] == declared
    found = [(f['type'], f['target'], f['dependency']) for f in current['findings']]
    assert set(found) == errors and len(found) == len(errors)
    assert set(current['reused']) == reused
    assert set(current['refreshed']) == {'main.o', 'helper.o'} - reused
    for entry in result['artifacts']:
        prefix = 'artifact://' + result['job_id'] + '/'
        assert entry['uri'].startswith(prefix)
        file = (folder / entry['uri'][len(prefix):]).resolve()
        assert file.is_relative_to(folder.resolve()) and file.is_file()
        assert hashlib.sha256(file.read_bytes()).hexdigest() == entry['sha256']
        assert file.stat().st_size == entry['bytes']
    verdict = {'passed': True, 'provenance': 'MANUAL_241880444_EXPECTED_GRAPHS',
               'expected_actual': actual, 'expected_declared': declared, 'expected_findings': sorted(errors),
               'reused': sorted(reused), 'job_id': result['job_id'], 'trace_id': result['trace_id'],
               'base': base, 'target': target, 'artifacts_verified': len(result['artifacts'])}
    save(folder / 'verification.json', verdict)
    return verdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--image-id', required=True)
    args = parser.parse_args()
    output = (ROOT / args.out).resolve()
    if not output.is_relative_to(ROOT / 'work') or output == ROOT / 'work' or output.exists():
        parser.error('Use a new output directory below work/')
    output.mkdir(parents=True)
    meta = {'student_id': '241880444', 'status': 'RUNNING', 'provenance': 'EXECUTION',
            'mode': 'E11-A_ONLY', 'time_utc': datetime.now(timezone.utc).isoformat(), 'cases': [],
            'source_sha': run(['git', 'rev-parse', 'HEAD'], ROOT).strip(),
            'working_tree': run(['git', 'status', '--porcelain'], ROOT).strip(), 'image_id': args.image_id}
    try:
        assert not meta['working_tree']
        project = output / 'controlled-project'
        fixture(project)
        run(['git', 'config', 'user.name', '241880444'], project)
        run(['git', 'config', 'user.email', '241880444@smail.nju.edu.cn'], project)
        c0 = run(['git', 'rev-parse', 'HEAD'], project).strip()
        source = project / 'main.c'
        source.write_text('#include "extra.h"\n' + source.read_text())
        c1 = commit(project, '241880444 E11-A C1 main include')

        def one(name, base, target, actual, declared, expected, reused):
            request = {'mode': 'e11-a', 'repo': str(project), 'base': base, 'target': target}
            folder = output / name
            result = execute(request, folder)
            meta['cases'].append(checks(result, folder, base, target, actual, declared, expected, reused))
            print(name, result['status'], len(expected), 'findings', flush=True)

        main_actual = {'main.o': ['config.h', 'extra.h', 'main.c'], 'helper.o': ['helper.c']}
        main_errors = BASE_ERRORS | {('MISSING', 'main.o', 'extra.h')}
        one('standard', c0, c1, main_actual, BASE_DECLARED, main_errors, set())
        helper = project / 'helper.c'
        helper.write_text('#include "extra.h"\n' + helper.read_text())
        c2 = commit(project, '241880444 E11-A C2 helper also includes extra.h')
        both_actual = {'main.o': ['config.h', 'extra.h', 'main.c'], 'helper.o': ['extra.h', 'helper.c']}
        both_errors = main_errors | {('MISSING', 'helper.o', 'extra.h')}
        one('extension-both-targets', c0, c2, both_actual, BASE_DECLARED, both_errors, set())
        makefile = project / 'Makefile'
        text = makefile.read_text().replace('main.o: main.c unused.h', 'main.o: main.c config.h extra.h')
        makefile.write_text(text.replace('helper.o: helper.c', 'helper.o: helper.c extra.h'))
        c3 = commit(project, '241880444 E11-A C3 declarations-only repair')
        one('extension-declarations-only', c2, c3, both_actual, both_actual, set(), {'main.o', 'helper.o'})
        file = output / 'standard/incremental-check.json'
        before = file.read_bytes()
        stale = copy.deepcopy(json.loads(before))
        stale['commit'] = c0
        try:
            check_envelope(stale, c1, 'incremental-check')
        except Failure as exc:
            assert exc.code == 'STALE_REPORT'
            save(output / 'expected-stale-rejection.json', {'passed': True, 'error_code': exc.code,
                 'expected_commit': c1, 'provided_commit': c0, 'original_report_unchanged': file.read_bytes() == before})
        else:
            raise AssertionError('Old report unexpectedly accepted')
        run(['git', 'bundle', 'create', str(output / 'project-history.bundle'), '--all'], project)
        save(output / 'dataset.json', {'source': 'course-generated controlled C/Make fixture with personal commits',
             'external_real_project': False, 'commits': {'C0': c0, 'C1': c1, 'C2': c2, 'C3': c3}})
        meta.update(status='PASSED', stale_report_rejected=True, e11_b_executed=False, e12_executed=False)
    except Exception as exc:
        meta.update(status='FAILED', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        save(output / 'summary.json', meta)
        print(json.dumps(meta, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
