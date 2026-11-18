"""Smoke test: the package and the schema module import cleanly."""

import natter
import natter.schema


def test_package_imports() -> None:
    assert natter.__doc__
    assert natter.schema.Report is not None
