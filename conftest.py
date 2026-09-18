import importlib.util
import pytest
import jinshu

def pytest_collection_modifyitems(items):
    # Only dependency-unavailable tests are skipped; no fake Mongo implementation.
    if importlib.util.find_spec("pymongo") is None:
        names={"test_mongo_increment_omits_conflicting_parent_default", "test_mongo_increment_keeps_non_overlapping_defaults"}
        for item in items:
            if item.name in names:
                item.add_marker(pytest.mark.skip(reason="pymongo unavailable in execution environment; Mongo integration not verified"))
