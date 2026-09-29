"""Validate a product CSV and generate Google Merchant, Meta and JSON-LD feeds."""

__version__ = "0.1.0"

from .google import render_google_feed  # noqa: E402
from .jsonld import product_jsonld, render_jsonld_html, render_jsonld_json  # noqa: E402
from .meta import render_meta_csv  # noqa: E402
from .model import Issue, Options, Product  # noqa: E402
from .parsing import check_gtin, parse_price  # noqa: E402
from .reader import ReaderError, parse_table, read_table  # noqa: E402
from .validate import process  # noqa: E402

__all__ = [
    "Issue", "Options", "Product", "ReaderError", "check_gtin", "parse_price", "parse_table",
    "process", "product_jsonld", "read_table", "render_google_feed", "render_jsonld_html",
    "render_jsonld_json", "render_meta_csv",
]
