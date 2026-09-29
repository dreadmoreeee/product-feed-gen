"""Make the package importable without installing it, and share small helpers."""
import datetime as dt
import pathlib
import sys

import pytest

TOOL_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from product_feed_gen.model import Options  # noqa: E402
from product_feed_gen.reader import RawRow  # noqa: E402
from product_feed_gen.validate import build_product  # noqa: E402

TODAY = dt.date(2026, 9, 29)

GOOD_ROW = {
    "id": "T-1",
    "title": "Oak Tray",
    "description": "A solid oak tray.",
    "link": "https://shop.example.ca/p/t-1",
    "image_link": "https://shop.example.ca/i/t-1.jpg",
    "availability": "in_stock",
    "price": "19.99 CAD",
    "brand": "Example Wood Co",
    "gtin": "4006381333931",
}


@pytest.fixture
def tool_dir():
    return TOOL_DIR


@pytest.fixture
def fixtures():
    return TOOL_DIR / "tests" / "fixtures"


@pytest.fixture
def options():
    return Options(today=TODAY)


@pytest.fixture
def make_product(options):
    """make_product(field=value, ...) -> validated Product built from a valid row."""

    def make(lang="en", opts=None, **overrides):
        values = dict(GOOD_ROW)
        values.update(overrides)
        return build_product(RawRow(2, values), lang, opts or options)

    return make

