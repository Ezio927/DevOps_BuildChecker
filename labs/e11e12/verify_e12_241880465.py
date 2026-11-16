"""核对 E12 跨仓库交接、五阶段身份及修复后的原始证据。"""
import argparse
import hashlib
import json
from pathlib import Path

from pipeline import check_envelope, save, verify_incremental
from test_a_handoff_241880465 import verify_handoff


def verify(source, consumer, output):
    """从实际产物重建验收判定，并保存可复核的任务和版本身份。"""
    source_bytes = (source / 'incremental-check.json').read_bytes()
    report = json.loads((consumer / 'incremental-check.json').read_text())
    verify_handoff(source_bytes, report)
    result = json.loads((consumer / 'result.json').read_text())
    assert result['status'] == 'SUCCEEDED'
    assert [stage['name'] for stage in result['stages']] == ['draft', 'full-check', 'incremental-check', 'repair', 'recheck']
    for name in ('draft', 'full-check', 'incremental-check', 'repair', 'recheck'):
        envelope = json.loads((consumer / (name + '.json')).read_text())
        commit = result['base_commit'] if name == 'full-check' else result['target_commit']
        check_envelope(envelope, commit, name)
        assert envelope['job_id'] == result['job_id']
        assert envelope['trace_id'] == result['trace_id']
    reference = json.loads((consumer / 'target-full/findings.json').read_text())
    verify_incremental(report['data'], reference, consumer / 'target-full', result['target_commit'])
    validation = json.loads((consumer / 'validation/validation.json').read_text())
    assert validation['accepted'] and all(validation['checks'].values())
    final = json.loads((consumer / 'final-full/findings.json').read_text())
    assert final['status'] == 'SUCCEEDED'
    assert not any(f['type'] == 'MISSING' for f in final['findings'])
    for item in result['artifacts']:
        prefix = 'artifact://' + result['job_id'] + '/'
        assert item['uri'].startswith(prefix)
        path = (consumer / item['uri'][len(prefix):]).resolve()
        assert path.is_relative_to(consumer.resolve())
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == item['sha256']
        assert len(data) == item['bytes']
    summary = {'passed': True, 'student_id': '241880465',
               'source_job_id': report['provenance']['source_job_id'],
               'job_id': result['job_id'], 'trace_id': result['trace_id'],
               'base_commit': result['base_commit'], 'target_commit': result['target_commit'],
               'artifacts_verified': len(result['artifacts']), 'validation': validation,
               'final_findings': final['findings']}
    save(output, summary)
    print(json.dumps(summary, ensure_ascii=False))


def main():
    """读取指定 A/B 证据目录并输出验证记录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.source, args.consumer, args.out)


if __name__ == '__main__':
    main()
