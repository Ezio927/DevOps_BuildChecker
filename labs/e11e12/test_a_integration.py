"""241880444: E11-A identity, artifact, and full-graph contract tests."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pipeline import Failure, check_envelope, load_artifact, verify_incremental


class AIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.sha = 'a' * 40
        self.findings = [{'type': 'MISSING', 'target': 'main.o', 'dependency': 'config.h'}]
        self.current = {'commit': self.sha, 'actual': {'main.o': ['config.h', 'main.c'], 'helper.o': ['helper.c']},
                        'declared': {'main.o': ['main.c'], 'helper.o': ['helper.c']}, 'findings': self.findings}
        self.reference = {'status': 'SUCCEEDED', 'findings': self.findings}
        for field, file in [('actual', 'actual-graph.json'), ('declared', 'declared-graph.json')]:
            rows = [{'target': target, 'dependency': dep}
                    for target, deps in self.current[field].items() for dep in deps]
            rows.append({'target': 'app', 'dependency': 'main.o'})
            (self.folder / file).write_text(json.dumps(rows))

    def test_accept_exact_object_graphs_and_findings(self):
        verify_incremental(self.current, self.reference, self.folder, self.sha)

    def test_same_findings_do_not_hide_wrong_actual_graph(self):
        data = copy.deepcopy(self.current)
        data['actual']['main.o'] = ['main.c']
        with self.assertRaises(Failure) as caught:
            verify_incremental(data, self.reference, self.folder, self.sha)
        self.assertEqual(caught.exception.code, 'GRAPH_MISMATCH')

    def test_same_findings_do_not_hide_wrong_declaration_graph(self):
        data = copy.deepcopy(self.current)
        data['declared']['helper.o'].append('unused.h')
        with self.assertRaises(Failure) as caught:
            verify_incremental(data, self.reference, self.folder, self.sha)
        self.assertEqual(caught.exception.code, 'DECLARATION_MISMATCH')

    def test_stale_payload_commit_is_rejected(self):
        data = dict(self.current, commit='b' * 40)
        with self.assertRaises(Failure) as caught:
            verify_incremental(data, self.reference, self.folder, self.sha)
        self.assertEqual(caught.exception.code, 'STALE_REPORT')

    def envelope(self):
        return {'schema_version': 'e11e12-1', 'commit': self.sha,
                'kind': 'incremental-check', 'status': 'SUCCEEDED'}

    def test_stale_envelope_is_rejected(self):
        with self.assertRaises(Failure) as caught:
            check_envelope(self.envelope(), 'b' * 40, 'incremental-check')
        self.assertEqual(caught.exception.code, 'STALE_REPORT')

    def test_wrong_artifact_kind_is_rejected(self):
        with self.assertRaises(Failure) as caught:
            check_envelope(self.envelope(), self.sha, 'full-check')
        self.assertEqual(caught.exception.code, 'ARTIFACT_TYPE_MISMATCH')

    def test_wrong_schema_is_rejected(self):
        data = dict(self.envelope(), schema_version='old')
        with self.assertRaises(Failure) as caught:
            check_envelope(data, self.sha, 'incremental-check')
        self.assertEqual(caught.exception.code, 'SCHEMA_MISMATCH')

    def test_changed_artifact_is_rejected(self):
        file = self.folder / 'report.json'
        file.write_text('{}')
        expected = hashlib.sha256(file.read_bytes()).hexdigest()
        file.write_text('{"changed":true}')
        with self.assertRaises(Failure) as caught:
            load_artifact(file, expected)
        self.assertEqual(caught.exception.code, 'ARTIFACT_HASH_MISMATCH')
