"""Read a product CSV: tolerant header names, optional explicit column mapping."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from .parsing import strip_accents

# canonical field -> accepted header spellings (after normalisation, see norm_header)
ALIASES: dict[str, str] = {
    "id": "id sku product_id item_id product_code code ref reference sku_id identifiant",
    "title": "title name product_name product_title titre nom",
    "description": "description desc product_description body details",
    "price": "price regular_price list_price prix prix_regulier",
    "sale_price": "sale_price special_price discount_price prix_solde prix_promo promo_price",
    "sale_price_effective_date": "sale_price_effective_date sale_dates sale_date sale_window",
    "sale_start": "sale_start sale_start_date sale_price_start sale_price_effective_date_start debut_solde",
    "sale_end": "sale_end sale_end_date sale_price_end sale_price_effective_date_end fin_solde",
    "currency": "currency currency_code devise",
    "availability": "availability stock_status stock disponibilite in_stock",
    "condition": "condition etat",
    "brand": "brand marque manufacturer vendor",
    "gtin": "gtin upc ean barcode isbn code_barres gtin8 gtin12 gtin13 gtin14",
    "mpn": "mpn manufacturer_part_number part_number",
    "image_link": "image_link image image_url main_image image_1 photo",
    "additional_image_links": (
        "additional_image_links additional_image_link additional_images other_images images"
    ),
    "link": "link url product_url product_link page_url lien",
    "shipping_weight": "shipping_weight weight poids",
    "google_product_category": "google_product_category google_category gpc",
    "product_type": "product_type category categorie type",
    "identifier_exists": "identifier_exists identifiers_exist has_identifiers",
    "price_valid_until": "price_valid_until valid_until",
    "shipping": "shipping shipping_rates livraison",
    "return_days": "return_days return_window days_to_return jours_retour",
    "return_fees": "return_fees return_fee return_shipping frais_retour",
}
# fields that may carry a language suffix: title_fr, description_en, link_fr ...
LANG_FIELDS = ("title", "description", "link")
LANGS = ("en", "fr")

FIELDS = frozenset(ALIASES) | frozenset(f"{f}_{lang}" for f in LANG_FIELDS for lang in LANGS)

_ALIAS_INDEX = {alias: name for name, words in ALIASES.items() for alias in words.split()}
_LANG_SUFFIX = re.compile(r"^(.*?)_(en|fr)(?:_ca)?$")


class ReaderError(Exception):
    """The CSV cannot be read or the mapping does not fit it."""


@dataclass
class RawRow:
    number: int  # record number; the header is row 1
    values: dict[str, str]


@dataclass
class Table:
    rows: list[RawRow] = field(default_factory=list)
    columns: dict[str, str] = field(default_factory=dict)  # canonical -> header in the file
    unmapped: list[str] = field(default_factory=list)
    encoding: str = "utf-8"

    def languages(self) -> list[str]:
        """Languages that have at least one column (title_fr ...); ['en'] when none do."""
        found = [lang for lang in LANGS if any(c.endswith(f"_{lang}") for c in self.columns)]
        return found or ["en"]


def norm_header(header: str) -> str:
    """'Prix Regulier ' -> 'prix_regulier'; 'g:price' -> 'g_price'."""
    return re.sub(r"[^a-z0-9]+", "_", strip_accents(header).lower()).strip("_")


def canonical_name(header: str) -> str | None:
    key = norm_header(header)
    if key.startswith("g_") and key[2:] in _ALIAS_INDEX:  # Google feed style: g:price
        key = key[2:]
    if key in _ALIAS_INDEX:
        return _ALIAS_INDEX[key]
    m = _LANG_SUFFIX.match(key)
    if m and _ALIAS_INDEX.get(m.group(1)) in LANG_FIELDS:
        return f"{_ALIAS_INDEX[m.group(1)]}_{m.group(2)}"
    return None


def decode(data: bytes) -> tuple[str, str]:
    """UTF-8 (with or without BOM); Excel's Windows-1252 as a fallback."""
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "cp1252"


def sniff_delimiter(text: str) -> str:
    first = text.split("\n", 1)[0]
    counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def parse_table(text: str, mapping: dict[str, str] | None = None) -> Table:
    """Turn CSV text into a Table. mapping is {canonical field: header name}."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=sniff_delimiter(text))
    try:
        headers = next(reader)
    except StopIteration:
        raise ReaderError("the CSV is empty") from None
    headers = [h.strip() for h in headers]
    chosen: dict[int, str] = {}  # column index -> canonical name

    for name, wanted in (mapping or {}).items():
        if name not in FIELDS:
            raise ReaderError(f"unknown field '{name}' in the column mapping")
        hits = [i for i, h in enumerate(headers) if norm_header(h) == norm_header(wanted)]
        if not hits:
            raise ReaderError(f"mapped column '{wanted}' (for {name}) is not in the CSV header: {headers}")
        chosen[hits[0]] = name

    taken = set(chosen.values())
    for i, header in enumerate(headers):
        if i in chosen or not header:
            continue
        name = canonical_name(header)
        if name is None or name in taken:
            continue
        chosen[i] = name
        taken.add(name)
    # an exact canonical header beats an alias that got there first
    for i, header in enumerate(headers):
        if i not in chosen and norm_header(header) in _ALIAS_INDEX:
            name = _ALIAS_INDEX[norm_header(header)]
            if norm_header(header) == name and name not in (mapping or {}):
                for j, other in list(chosen.items()):
                    if other == name:
                        del chosen[j]
                chosen[i] = name

    table = Table(
        columns={name: headers[i] for i, name in sorted(chosen.items())},
        unmapped=[h for i, h in enumerate(headers) if i not in chosen and h],
    )
    for number, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        table.rows.append(
            RawRow(number, {name: (cells[i].strip() if i < len(cells) else "") for i, name in chosen.items()})
        )
    return table


def read_table(path: str | Path, mapping: dict[str, str] | None = None) -> Table:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise ReaderError(f"cannot read {path}: {exc.strerror or exc}") from None
    text, encoding = decode(data)
    table = parse_table(text, mapping)
    table.encoding = encoding
    return table
