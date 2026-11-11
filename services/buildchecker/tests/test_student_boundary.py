"""241880444: independent expectations for transitive phony prerequisites."""
import pytest

from buildchecker.fullcheck import Unsupported, declaration_graph


def test_transitive_phony_prerequisites_deduplicate_real_headers(tmp_path):
    database = tmp_path / "make-db.txt"
    database.write_text(
        "# Files\n.PHONY: headers public\n"
        "headers: public needed.h\npublic: nested.h needed.h\n"
        "unit.o: unit.c headers | build-dir\n# files hash-table stats:\n",
        encoding="utf-8",
    )
    graph = declaration_graph(database, "/course/project")
    assert set(graph) == {"unit.o"}
    assert set(graph["unit.o"]["dependencies"]) == {"unit.c", "needed.h", "nested.h"}
    assert graph["unit.o"]["order_only"] == ["build-dir"]


def test_phony_cycle_is_rejected_instead_of_returning_a_partial_graph(tmp_path):
    database = tmp_path / "make-db.txt"
    database.write_text(
        "# Files\n.PHONY: first second\nfirst: second\nsecond: first\n"
        "unit.o: unit.c first\n# files hash-table stats:\n", encoding="utf-8",
    )
    with pytest.raises(Unsupported, match="Cycle"):
        declaration_graph(database, "/course/project")
