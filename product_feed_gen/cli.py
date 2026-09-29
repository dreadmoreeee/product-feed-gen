"""Command line interface."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .google import render_google_feed
from .jsonld import render_jsonld_html, render_jsonld_json
from .meta import render_meta_csv
from .model import LANG_TAGS, Options, Product
from .parsing import CURRENCIES
from .reader import FIELDS, ReaderError, read_table
from .report import EXTENSIONS, FORMATS, render
from .validate import detect_languages, process

OUTPUTS = ("google", "meta", "jsonld")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="product-feed-gen",
        description="Validate a product CSV and generate a Google Merchant feed, a Meta catalog CSV "
        "and schema.org JSON-LD. The checks cover common Merchant Center requirements; "
        "this is not an official validator.",
    )
    p.add_argument("csv", help="products CSV (UTF-8 or Windows-1252; comma, semicolon, tab or pipe separated)")
    p.add_argument("--out", metavar="DIR", help="write feeds and the report here (without it, only the report is printed)")
    p.add_argument("--formats", default=",".join(OUTPUTS), help="comma list of google, meta, jsonld (default: all)")
    p.add_argument("--lang", default="auto", choices=["auto", *LANG_TAGS], help="auto: en-CA and fr-CA when the CSV has _en/_fr columns, else en-CA")
    p.add_argument("--currency", default="CAD", help="currency when a row has none (default: CAD)")
    p.add_argument("--map", action="append", default=[], metavar="FIELD=HEADER", help="use this CSV header for a field, e.g. --map price=\"Regular price\"")
    p.add_argument("--mapping", metavar="FILE", help="JSON file with {field: header} pairs")
    p.add_argument("--report", choices=FORMATS, default="text", help="report format (default: text)")
    p.add_argument("--report-file", metavar="FILE", help="write the report here instead of stdout")
    p.add_argument("--strict", action="store_true", help="exit with status 1 if any product has an error")
    p.add_argument("--include-invalid", action="store_true", help="keep products with errors in the feeds")
    p.add_argument("--allow-http", action="store_true", help="accept http:// links and images with a warning instead of an error")
    p.add_argument("--country", default="CA", help="country of the return policy in JSON-LD (default: CA)")
    p.add_argument("--tz-offset", default="-05:00", help="UTC offset for date-only sale windows (default: -05:00)")
    p.add_argument("--today", metavar="YYYY-MM-DD", help="pretend it is this day (sale windows, expired dates); for reproducible output")
    p.add_argument("--shop-name", default="Product feed", help="channel title of the Google feed")
    p.add_argument("--shop-url", default="", help="channel link of the Google feed (default: the site of the first product)")
    p.add_argument("--shop-description", default="", help="channel description of the Google feed")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _fail(message: str) -> int:
    print(f"product-feed-gen: {message}", file=sys.stderr)
    return 2


def _load_mapping(args: argparse.Namespace) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if args.mapping:
        try:
            data = json.loads(Path(args.mapping).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ReaderError(f"cannot read mapping file: {exc}") from None
        if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
            raise ReaderError("the mapping file must be a JSON object of {field: header}")
        mapping.update(data)
    for item in args.map:
        name, sep, header = item.partition("=")
        if not sep or not name.strip() or not header.strip():
            raise ReaderError(f"--map expects FIELD=HEADER, got '{item}'")
        mapping[name.strip()] = header.strip()
    unknown = sorted(set(mapping) - FIELDS)
    if unknown:
        raise ReaderError(f"unknown field(s) in the mapping: {', '.join(unknown)}; known: {', '.join(sorted(FIELDS))}")
    return mapping


def _default_shop_url(products: list[Product]) -> str:
    for p in products:
        parts = urlsplit(p.link)
        if parts.scheme in ("http", "https") and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}/"
    return ""


def write_outputs(products: list[Product], out: Path, formats: list[str], args: argparse.Namespace, options: Options) -> list[Path]:
    """Write the feeds for every language present; return the paths written."""
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for tag in dict.fromkeys(p.tag for p in products):
        batch = [p for p in products if p.tag == tag and (args.include_invalid or not p.errors)]
        shop_url = args.shop_url or _default_shop_url(batch)
        files: dict[str, str] = {}
        if "google" in formats:
            files[f"google-feed.{tag}.xml"] = render_google_feed(batch, tag, args.shop_name, shop_url, args.shop_description)
        if "meta" in formats:
            files[f"meta-catalog.{tag}.csv"] = render_meta_csv(batch)
        if "jsonld" in formats:
            files[f"jsonld.{tag}.json"] = render_jsonld_json(batch, options.today)
            files[f"jsonld.{tag}.html"] = render_jsonld_html(batch, options.today)
        for name, content in files.items():
            path = out / name
            path.write_text(content, encoding="utf-8", newline="")
            written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)

    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    if not formats or any(f not in OUTPUTS for f in formats):
        return _fail(f"--formats takes a comma list of {', '.join(OUTPUTS)}")
    if not re.fullmatch(r"[+-]\d{2}:\d{2}", args.tz_offset):
        return _fail("--tz-offset must look like -05:00")
    if args.currency.upper() not in CURRENCIES:
        return _fail(f"--currency '{args.currency}' is not an ISO 4217 code")
    options = Options(
        default_currency=args.currency.upper(),
        allow_http=args.allow_http,
        tz_offset=args.tz_offset,
        country=args.country.upper(),
    )
    if args.today:
        try:
            options.today = dt.date.fromisoformat(args.today)
        except ValueError:
            return _fail("--today must be YYYY-MM-DD")

    try:
        table = read_table(args.csv, _load_mapping(args))
    except ReaderError as exc:
        return _fail(str(exc))
    if not table.rows:
        return _fail("the CSV has a header but no product rows")
    langs = detect_languages(table, args.lang)
    products = process(table, options, langs)

    report = render(args.report, products, Path(args.csv).name, args.include_invalid)
    notes: list[str] = []
    if table.unmapped:
        notes.append(f"columns not used: {', '.join(table.unmapped)}")
    if args.report_file:
        Path(args.report_file).write_text(report, encoding="utf-8", newline="")
        notes.append(f"wrote {args.report_file}")
    else:
        sys.stdout.write(report)
    if args.out:
        out = Path(args.out)
        written = write_outputs(products, out, formats, args, options)
        report_path = out / f"report.{EXTENSIONS[args.report]}"
        if not args.report_file:
            report_path.write_text(report, encoding="utf-8", newline="")
            written.append(report_path)
        notes += [f"wrote {path}" for path in written]
    for note in notes:
        print(note, file=sys.stderr)

    if args.strict and any(p.errors for p in products):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
