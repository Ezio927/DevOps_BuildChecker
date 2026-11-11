"""Independent expected graphs for 241880444's three personal experiments."""
from pathlib import Path
import tempfile
import unittest

from student_241880444 import correct_dependency_case, declaration_only_case, helper_lifecycle_case


class Student241880444Tests(unittest.TestCase):
    def test_declaration_changes_recompute_errors_without_refreshing_actual_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            declaration_only_case(Path(tmp))

    def test_helper_header_missing_correct_and_redundant_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper_lifecycle_case(Path(tmp))

    def test_correct_dependency_addition_changes_graph_not_error_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            correct_dependency_case(Path(tmp))
