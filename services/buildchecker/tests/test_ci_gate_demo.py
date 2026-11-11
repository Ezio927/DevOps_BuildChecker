"""Corrected E7 teaching oracle; the preceding commit deliberately expected failure."""
from buildchecker.cli import main


def test_version_exit_code_gate_demo():
    assert main(["version"]) == 0
