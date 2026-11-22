"""Exercise the E13 scanner using parser lines and fabricated credentials."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scan_runtime_logs import main


class RuntimeScanTests(unittest.TestCase):
    def scan(self, filename, contents):
        with TemporaryDirectory() as folder:
            path = Path(folder) / filename
            path.write_text(contents, encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = main([str(path)])
        return code, output.getvalue()

    def test_parser_token_pointer_is_clean(self):
        source = "\n".join([
            "token" + " = jsmn_alloc_token(parser, tokens, num_tokens);",
            "token" + " = &tokens[parser->toknext - 1];",
        ])
        code, log = self.scan("jsmn.h", source)
        self.assertEqual(code, 0, log)

    def test_c_token_string_remains_a_hit(self):
        fabricated = "synthetic-value-vx847902"
        code, log = self.scan("bad.h", "token" + f' = "{fabricated}";\n')
        self.assertEqual(code, 1, log)
        self.assertNotIn(fabricated, log)

    def test_log_does_not_get_c_source_exception(self):
        code, log = self.scan("runtime.log", "token" + " = jsmn_alloc_token(parser, tokens, num_tokens);\n")
        self.assertEqual(code, 1, log)

    def test_standard_key_detector_still_checks_c_source(self):
        fabricated = "sk-" + "classroomSynthetic8348demo"
        code, log = self.scan("bad.c", f'write_fixture_log("{fabricated}");\n')
        self.assertEqual(code, 1, log)
        self.assertNotIn(fabricated, log)
