"""Per-product problem report as text, Markdown or JSON."""
from __future__ import annotations

import json

from .model import Product

FORMATS = ("text", "markdown", "json")
EXTENSIONS = {"text": "txt", "markdown": "md", "json": "json"}


def summarize(products: list[Product]) -> dict:
    """Counts per language tag."""
    result: dict[str, dict[str, int]] = {}
    for p in products:
        counts = result.setdefault(p.tag, {"products": 0, "ok": 0, "warning": 0, "error": 0})
        counts["products"] += 1
        counts[p.status] += 1
    return result


def _shorten(text: str, width: int = 48) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def _summary_line(tag: str, c: dict, multi: bool) -> str:
    prefix = f"{tag}: " if multi else ""
    return (
        f"{prefix}{c['products']} products: {c['ok']} ok, {c['warning']} with warnings only, "
        f"{c['error']} with errors"
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def render_text(products: list[Product], source: str = "products.csv", include_invalid: bool = False) -> str:
    summary = summarize(products)
    multi = len(summary) > 1
    lines = [f"product-feed-gen report for {source}", ""]
    for tag in summary:
        batch = [p for p in products if p.tag == tag and p.issues]
        if multi:
            lines.append(f"[{tag}]")
        for p in batch:
            head = f"row {p.row}  {p.id or '(no id)'}  {_shorten(p.title)}"
            lines.append(f"{head}  -- {_plural(len(p.errors), 'error')}, {_plural(len(p.warnings), 'warning')}")
            for i in p.issues:
                lines.append(f"  {i.severity.upper():<8} {i.code:<24} {i.message}")
        if batch:
            lines.append("")
    for tag, counts in summary.items():
        lines.append(_summary_line(tag, counts, multi))
    if any(p.errors for p in products):
        lines.append("Products with errors " + ("are kept in the feeds (--include-invalid)." if include_invalid else "are left out of the feeds."))
    return "\n".join(lines) + "\n"


def render_markdown(products: list[Product], source: str = "products.csv", include_invalid: bool = False) -> str:
    summary = summarize(products)
    lines = [f"# Product feed report: {source}", ""]
    lines += ["| Language | Products | OK | Warnings only | Errors |", "|---|---|---|---|---|"]
    for tag, c in summary.items():
        lines.append(f"| {tag} | {c['products']} | {c['ok']} | {c['warning']} | {c['error']} |")
    lines.append("")
    for tag in summary:
        batch = [p for p in products if p.tag == tag and p.issues]
        if not batch:
            continue
        lines += [f"## {tag}: products with problems", ""]
        lines += ["| Row | ID | Severity | Field | Problem |", "|---|---|---|---|---|"]
        for p in batch:
            for i in p.issues:
                message = i.message.replace("|", "\\|")
                lines.append(f"| {p.row} | {p.id or '-'} | {i.severity} | {i.field} | {message} |")
        lines.append("")
    if any(p.errors for p in products):
        note = "kept in the feeds" if include_invalid else "left out of the feeds"
        lines += [f"Products with errors are {note}.", ""]
    return "\n".join(lines)


def render_json(products: list[Product], source: str = "products.csv", include_invalid: bool = False) -> str:
    data = {
        "source": source,
        "include_invalid": include_invalid,
        "summary": summarize(products),
        "products": [
            {
                "row": p.row,
                "id": p.id,
                "title": p.title,
                "language": p.tag,
                "status": p.status,
                "issues": [i.to_dict() for i in p.issues],
            }
            for p in products
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render(fmt: str, products: list[Product], source: str = "products.csv", include_invalid: bool = False) -> str:
    renderer = {"text": render_text, "markdown": render_markdown, "json": render_json}[fmt]
    return renderer(products, source, include_invalid)
