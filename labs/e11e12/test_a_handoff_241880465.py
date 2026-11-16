"""核对跨仓库消费记录与原始 A 报告的身份、摘要和数据。"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline import check_envelope, save
from server import Store


def verify_handoff(source_bytes, consumer):
    """验证 B 的消费封装完整保留 A 报告的数据与来源。"""
    source = json.loads(source_bytes)
    check_envelope(source, source['commit'], 'incremental-check')
    check_envelope(consumer, source['commit'], 'incremental-check')
    expected = {
        'source_job_id': source['job_id'],
        'source_trace_id': source['trace_id'],
        'source_kind': 'incremental-check',
        'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
    }
    if source['kind'] != 'incremental-check' or consumer['kind'] != 'incremental-check':
        raise ValueError('ARTIFACT_TYPE_MISMATCH')
    if consumer.get('provenance') != expected:
        raise ValueError('PROVENANCE_MISMATCH')
    if consumer['commit'] != source['commit'] or source['data']['commit'] != source['commit']:
        raise ValueError('STALE_REPORT')
    if consumer['data'] != source['data']:
        raise ValueError('PAYLOAD_MISMATCH')
    return True


class Handoff241880465Tests(unittest.TestCase):
    """覆盖来源被替换和发现相同但实际图被改变的情况。"""

    def setUp(self):
        """建立确定的跨仓库报告及摘要。"""
        self.source = {'schema_version': 'e11e12-1', 'status': 'SUCCEEDED',
                       'kind': 'incremental-check', 'commit': 'a'*40,
                       'job_id': 'job-source', 'trace_id': 'trace-source',
                       'data': {'commit': 'a'*40, 'actual': {'main.o': ['main.c']}, 'findings': []}}
        self.raw = json.dumps(self.source).encode()
        self.consumer = copy.deepcopy(self.source)
        self.consumer['provenance'] = {'source_job_id': 'job-source', 'source_trace_id': 'trace-source',
                                      'source_kind': 'incremental-check', 'source_sha256': hashlib.sha256(self.raw).hexdigest()}

    def test_exact_handoff(self):
        """完整交接应通过。"""
        self.assertTrue(verify_handoff(self.raw, self.consumer))

    def test_changed_graph_with_same_findings(self):
        """发现数量相同也必须拒绝实际图变化。"""
        self.consumer['data']['actual']['main.o'].append('extra.h')
        with self.assertRaisesRegex(ValueError, 'PAYLOAD_MISMATCH'):
            verify_handoff(self.raw, self.consumer)

    def test_changed_source_identity(self):
        """拒绝来源任务被替换的消费记录。"""
        self.consumer['provenance']['source_job_id'] = 'job-other'
        with self.assertRaisesRegex(ValueError, 'PROVENANCE_MISMATCH'):
            verify_handoff(self.raw, self.consumer)

    def test_changed_payload_commit(self):
        """拒绝封装版本正确但内部报告版本过期的交接。"""
        source = copy.deepcopy(self.source)
        source['data']['commit'] = 'b'*40
        raw = json.dumps(source).encode()
        self.consumer['provenance']['source_sha256'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, 'STALE_REPORT'):
            verify_handoff(raw, self.consumer)

    def test_restarted_store_marks_unfinished_jobs(self):
        """用持久化状态验证重启恢复，未完成任务失败且成功任务可查询。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for status in ('QUEUED', 'RUNNING', 'SUCCEEDED'):
                state = {'job_id': 'job-' + status, 'status': status,
                         'idempotency_key': status, 'request_hash': status}
                save(root / state['job_id'] / 'state.json', state)
            store = Store(root)
            try:
                for status in ('QUEUED', 'RUNNING'):
                    recovered = store.jobs['job-' + status]
                    self.assertEqual(recovered['status'], 'FAILED')
                    self.assertEqual(recovered['error']['code'], 'SERVER_RESTARTED')
                    self.assertEqual(json.loads((root / recovered['job_id'] / 'state.json').read_text()), recovered)
                self.assertEqual(store.jobs['job-SUCCEEDED']['status'], 'SUCCEEDED')
            finally:
                store.pool.shutdown()
