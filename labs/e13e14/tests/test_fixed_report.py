"""验证 B 入口实际调用交接报告哈希校验。"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'e11e12'))
import pipeline


class FixedReportTests(unittest.TestCase):
    def test_changed_bytes_rejected_before_repair(self):
        """通过流水线入口提交篡改报告，确认修复没有执行。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / 'fixed.json'
            report.write_text(json.dumps({'schema_version': 'e11e12-1'}), encoding='utf-8')
            digest = hashlib.sha256(report.read_bytes()).hexdigest()
            report.write_bytes(report.read_bytes() + b'\n')
            request = {'mode': 'e11-b', 'repo': str(root), 'base': 'a' * 40,
                       'target': 'a' * 40, 'candidate': str(root / 'Dockerfile'),
                       'fixed_report': str(report), 'fixed_report_sha256': digest}
            def built(*args, **kwargs):
                """隔离构建步骤，生成流水线需要的构建结果文件。"""
                folder = args[2]
                folder.mkdir(parents=True)
                result = {'status': 'SUCCEEDED'}
                (folder / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                return result

            with patch.object(pipeline, 'snapshot', return_value='a' * 40), \
                 patch('draft.autobuild.auto_build', side_effect=built), \
                 patch.object(pipeline, 'patch') as repair:
                result = pipeline.execute(request, root / 'out')
            self.assertEqual(result['status'], 'FAILED')
            self.assertEqual(result['error']['code'], 'ARTIFACT_HASH_MISMATCH')
            repair.assert_not_called()


if __name__ == '__main__':
    unittest.main()
