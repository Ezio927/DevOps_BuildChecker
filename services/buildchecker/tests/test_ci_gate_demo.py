"""Intentional wrong oracle for the E7 rejection exercise; not an algorithm defect."""
from buildchecker.cli import main


def test_version_exit_code_gate_demo():
    assert main(["version"]) == 1
