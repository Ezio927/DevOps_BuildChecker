"""241880465 的 E11-A 端到端复用与过期结果拒绝验证。"""
import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline
from lab import commit, fixture, run


def verify_case(folder, base, target, extra, reused):
    """核对真实流水线的图、发现、版本身份和全部产物摘要。"""
    result = json.loads((folder / 'result.json').read_text())
    assert result['status'] == 'SUCCEEDED', result.get('error')
    assert result['base_commit'] == base and result['target_commit'] == target
    assert [s['name'] for s in result['stages']] == ['full-check', 'incremental-check']
    expected_actual = {'main.o': ['config.h', 'main.c'], 'helper.o': ['helper.c']}
    expected_findings = {('MISSING', 'main.o', 'config.h'), ('REDUNDANT', 'main.o', 'unused.h')}
    if extra:
        expected_actual['main.o'] = ['config.h', 'extra.h', 'main.c']
        expected_findings.add(('MISSING', 'main.o', 'extra.h'))
    current = json.loads((folder / 'incremental-report.json').read_text())
    assert current['commit'] == target
    assert current['actual'] == expected_actual
    assert current['declared'] == {'main.o': ['main.c', 'unused.h'], 'helper.o': ['helper.c']}
    assert {(f['type'], f['target'], f['dependency']) for f in current['findings']} == expected_findings
    assert current['reused'] == (['main.o', 'helper.o'] if reused else [])
    assert current['refreshed'] == ([] if reused else ['main.o', 'helper.o'])
    assert current['added'] == ([['MISSING', 'main.o', 'extra.h']] if extra else [])
    assert current['resolved'] == []
    baseline = json.loads((folder / 'baseline-cache.json').read_text())
    edges = json.loads((folder / 'baseline-full/actual-graph.json').read_text())
    assert baseline['actual'] == {t: sorted({e['dependency'] for e in edges if e['target'] == t}) for t in ('main.o', 'helper.o')}
    for kind, sha in [('full-check', base), ('incremental-check', target)]:
        envelope = json.loads((folder / (kind + '.json')).read_text())
        pipeline.check_envelope(envelope, sha, kind)
        assert envelope['job_id'] == result['job_id'] and envelope['trace_id'] == result['trace_id']
    for item in result['artifacts']:
        prefix = 'artifact://' + result['job_id'] + '/'
        assert item['uri'].startswith(prefix)
        file = (folder / item['uri'][len(prefix):]).resolve()
        assert file.is_relative_to(folder.resolve())
        assert hashlib.sha256(file.read_bytes()).hexdigest() == item['sha256']
        assert file.stat().st_size == item['bytes']
    pipeline.save(folder / 'personal-verification.json', {'passed': True, 'student_id': '241880465', 'artifacts_verified': len(result['artifacts'])})


def exercise(out):
    """建立三个真实提交，执行普通代码、include 变化和故障注入场景。"""
    out.mkdir(parents=True, exist_ok=False)
    project = out / 'project'
    fixture(project)
    base = run(['git', 'rev-parse', 'HEAD'], project).strip()
    (project / 'helper.c').write_text('int helper(void){return 0+0;}\n', encoding='utf-8')
    body = commit(project, '241880465 E11 普通函数体变化')
    request = {'mode': 'e11-a', 'repo': str(project.resolve()), 'base': base, 'target': body}
    pipeline.execute(request, out / 'body')
    verify_case(out / 'body', base, body, extra=False, reused=True)
    source = project / 'main.c'
    source.write_text('#include "extra.h"\n' + source.read_text(), encoding='utf-8')
    include = commit(project, '241880465 E11 新增直接包含')
    request = dict(request, base=body, target=include)
    pipeline.execute(request, out / 'include')
    verify_case(out / 'include', body, include, extra=True, reused=False)
    real_scan = pipeline.scan

    def stale_scan(project_path, old=None):
        """模拟下游返回旧提交数据，保留真实扫描的图与发现。"""
        report = real_scan(project_path, old)
        if old is not None:
            report['commit'] = body
        return report

    with patch.object(pipeline, 'scan', side_effect=stale_scan):
        rejected = pipeline.execute(request, out / 'stale')
    assert rejected['status'] == 'FAILED'
    assert rejected['error']['code'] == 'STALE_REPORT'
    assert [s['name'] for s in rejected['stages']] == ['full-check']
    assert not (out / 'stale/incremental-check.json').exists()
    assert not (out / 'stale/candidate.patch').exists()
    run(['git', 'bundle', 'create', str((out / 'project-history.bundle').resolve()), '--all'], project)
    pipeline.save(out / 'summary.json', {'passed': True, 'student_id': '241880465', 'body_reuse': True, 'include_refresh': True, 'stale_rejected': True, 'source_sha': run(['git', 'rev-parse', 'HEAD'], pipeline.ROOT).strip(), 'dataset': 'course-generated with personal Git commits', 'commits': {'base': base, 'body': body, 'include': include}})


class Student241880465IntegrationTests(unittest.TestCase):
    """通过正式 execute 入口检查个人 E11-A 场景。"""

    def test_body_reuse_and_stale_pipeline_rejection(self):
        """验证动态基线复用、新增依赖刷新和错误版本中止。"""
        with tempfile.TemporaryDirectory() as directory:
            exercise(Path(directory) / 'evidence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    exercise(args.out.resolve())
    print('E11-A 个人场景全部通过')
