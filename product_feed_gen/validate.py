"""Turn raw rows into normalised Products and check them.

The checks cover common Merchant Center requirements. They are not the
official validator: Merchant Center may still reject or warn about things
that are not tested here.
"""
from __future__ import annotations

from decimal import Decimal

from . import parsing as ps
from .model import ERROR, LANG_TAGS, WARNING, Options, Product, Shipping
from .reader import LANG_FIELDS, RawRow, Table

TITLE_MAX = 150
DESCRIPTION_MAX = 5000
ID_MAX = 50
MAX_ADDITIONAL_IMAGES = 10


def _resolve(values: dict[str, str], name: str, lang: str) -> tuple[str, bool]:
    """Value of a bilingual field for one language; True if it fell back to the base column."""
    if name not in LANG_FIELDS:
        return values.get(name, ""), False
    specific = f"{name}_{lang}"
    if values.get(specific):
        return values[specific], False
    base = values.get(name, "")
    return base, bool(base) and specific in values


def _price(p: Product, text: str, label: str) -> tuple[Decimal | None, str | None]:
    try:
        return ps.parse_price(text)
    except ValueError as exc:
        p.add(ERROR, "price-format", label, str(exc))
        return None, None


def build_product(row: RawRow, lang: str, options: Options) -> Product:
    """Normalise one row for one language and record every problem found."""
    v = row.values
    p = Product(row=row.number, lang=lang, return_country=options.country)
    add = p.add

    def required(name: str, label: str | None = None) -> str:
        value, fell_back = _resolve(v, name, lang)
        label = label or name
        if not value:
            add(ERROR, f"{label}-missing", label, f"{label} is required")
        elif fell_back:
            add(WARNING, "lang-fallback", label, f"{label}_{lang} is empty; using {label}")
        return value

    # --- core text attributes
    p.id = required("id")
    if len(p.id) > ID_MAX:
        add(ERROR, "id-too-long", "id", f"id has {len(p.id)} characters; the limit is {ID_MAX}")
    p.title = required("title")
    if len(p.title) > TITLE_MAX:
        add(ERROR, "title-too-long", "title", f"title has {len(p.title)} characters; the limit is {TITLE_MAX}")
    elif len(p.title) > 10 and p.title.isupper():
        add(WARNING, "title-all-caps", "title", "title is all capitals; Merchant Center may disapprove promotional-looking titles")
    p.description = required("description")
    if len(p.description) > DESCRIPTION_MAX:
        add(ERROR, "description-too-long", "description",
            f"description has {len(p.description)} characters; the limit is {DESCRIPTION_MAX}")

    # --- urls
    p.link = required("link")
    p.image_link = required("image_link")
    for name, url in (("link", p.link), ("image_link", p.image_link)):
        problem = ps.check_url(url, options.allow_http) if url else None
        if problem:
            add(problem[0], f"{name}-url", name, f"{name} '{url}' {problem[1]}")
    p.additional_image_links = ps.split_list(v.get("additional_image_links", ""))
    if len(p.additional_image_links) > MAX_ADDITIONAL_IMAGES:
        add(ERROR, "additional-images-count", "additional_image_links",
            f"{len(p.additional_image_links)} additional images; the limit is {MAX_ADDITIONAL_IMAGES}")
    for url in p.additional_image_links:
        problem = ps.check_url(url, options.allow_http)
        if problem:
            add(problem[0], "additional-image-url", "additional_image_links", f"'{url}' {problem[1]}")

    # --- availability and condition
    raw = v.get("availability", "")
    if not raw:
        add(ERROR, "availability-missing", "availability", "availability is required")
    else:
        p.availability = ps.parse_availability(raw) or ""
        if not p.availability:
            add(ERROR, "availability-value", "availability",
                f"availability '{raw}' is not one of in_stock, out_of_stock, preorder, backorder")
    raw = v.get("condition", "")
    if raw:
        cond = ps.parse_condition(raw)
        if cond:
            p.condition = cond
        else:
            add(ERROR, "condition-value", "condition", f"condition '{raw}' is not one of new, used, refurbished")

    # --- price, currency, sale price
    currency_col = v.get("currency", "").strip().upper()
    if currency_col and currency_col not in ps.CURRENCIES:
        add(ERROR, "currency-value", "currency", f"currency '{currency_col}' is not an ISO 4217 code")
        currency_col = ""
    codes: set[str] = set()
    raw = v.get("price", "")
    if not raw:
        add(ERROR, "price-missing", "price", "price is required")
    else:
        p.price, code = _price(p, raw, "price")
        if code:
            codes.add(code)
    raw = v.get("sale_price", "")
    if raw:
        p.sale_price, code = _price(p, raw, "sale_price")
        if code:
            codes.add(code)
    if len(codes) > 1:
        add(ERROR, "currency-conflict", "currency", f"price and sale_price use different currencies ({', '.join(sorted(codes))})")
    if currency_col and codes and currency_col not in codes:
        add(ERROR, "currency-conflict", "currency", f"currency column says {currency_col} but the price says {', '.join(sorted(codes))}")
    p.currency = (sorted(codes)[0] if codes else "") or currency_col or options.default_currency.upper()
    if p.price is not None and p.sale_price is not None and p.sale_price >= p.price:
        add(ERROR, "sale-price-not-lower", "sale_price",
            f"sale_price {p.sale_price} must be lower than price {p.price}")

    _sale_window(p, v, options)
    if v.get("price_valid_until"):
        try:
            p.price_valid_until = ps.parse_date(v["price_valid_until"])
            if p.price_valid_until < options.today:
                add(WARNING, "price-valid-until-past", "price_valid_until",
                    f"price_valid_until {p.price_valid_until} is in the past")
        except ValueError as exc:
            add(ERROR, "price-valid-until-format", "price_valid_until", str(exc))

    # --- identifiers
    p.brand = v.get("brand", "")
    p.mpn = v.get("mpn", "")
    raw = v.get("identifier_exists", "")
    if raw:
        p.identifier_exists = ps.parse_yes_no(raw)
        if p.identifier_exists is None:
            add(ERROR, "identifier-exists-value", "identifier_exists", f"identifier_exists '{raw}' is not yes or no")
    if v.get("gtin"):
        p.gtin, problem = ps.check_gtin(v["gtin"])
        if problem:
            add(ERROR, "gtin-invalid", "gtin", f"gtin '{v['gtin']}': {problem}")
    no_ids = p.identifier_exists is False
    if not no_ids:
        if not p.brand:
            add(ERROR, "brand-missing", "brand", "brand is required (or set identifier_exists to no)")
        if not p.gtin and not p.mpn:
            add(ERROR, "identifier-missing", "gtin",
                "provide a gtin or an mpn (or set identifier_exists to no for products without one)")
    elif p.gtin or p.mpn:
        add(WARNING, "identifier-conflict", "identifier_exists", "identifier_exists is no but a gtin or mpn is given")
    if not p.brand and no_ids:
        add(WARNING, "brand-missing-meta", "brand", "no brand; Meta catalogs require one")

    # --- optional attributes
    p.google_product_category = v.get("google_product_category", "")
    p.product_type = v.get("product_type", "")
    if not p.category:
        add(WARNING, "category-missing", "google_product_category",
            "no google_product_category or product_type; recommended for matching and reporting")
    if v.get("shipping_weight"):
        try:
            p.weight_value, p.weight_unit, assumed = ps.parse_weight(v["shipping_weight"])
            if assumed:
                add(WARNING, "weight-unit-assumed", "shipping_weight", f"no unit in '{v['shipping_weight']}'; assuming kg")
        except ValueError as exc:
            add(ERROR, "shipping-weight-format", "shipping_weight", str(exc))
    _shipping(p, v.get("shipping", ""))
    _returns(p, v)
    return p


def _sale_window(p: Product, v: dict[str, str], options: Options) -> None:
    start_text, end_text = v.get("sale_start", ""), v.get("sale_end", "")
    if not (start_text or end_text) and v.get("sale_price_effective_date"):
        start_text, _, end_text = (s.strip() for s in v["sale_price_effective_date"].partition("/"))
    try:
        if start_text:
            p.sale_start, p.sale_start_date = ps.parse_when(start_text, options.tz_offset)
        if end_text:
            p.sale_end, p.sale_end_date = ps.parse_when(end_text, options.tz_offset, end=True)
    except ValueError as exc:
        p.sale_start = p.sale_end = ""
        p.sale_start_date = p.sale_end_date = None
        p.add(ERROR, "sale-date-format", "sale_price_effective_date", str(exc))
        return
    if p.sale_start_date and p.sale_end_date and p.sale_end_date < p.sale_start_date:
        p.add(ERROR, "sale-window-order", "sale_price_effective_date", "the sale ends before it starts")
    if (p.sale_start or p.sale_end) and p.sale_price is None:
        p.add(WARNING, "sale-dates-without-price", "sale_price_effective_date", "sale dates given but there is no sale_price")
    if p.sale_price is not None and p.sale_end_date and p.sale_end_date < options.today:
        p.add(WARNING, "sale-ended", "sale_price_effective_date", f"the sale ended on {p.sale_end_date}")
    if p.sale_price is not None and bool(p.sale_start) != bool(p.sale_end):
        p.add(WARNING, "sale-window-open", "sale_price_effective_date", "the sale window has only one end; give both start and end")


def _shipping(p: Product, text: str) -> None:
    for chunk in (c.strip() for c in text.replace(";", "|").split("|")):
        if not chunk:
            continue
        country, sep, rest = chunk.partition(":")
        country = country.strip().upper()
        if not sep or len(country) != 2 or not country.isalpha():
            p.add(ERROR, "shipping-format", "shipping", f"shipping '{chunk}' must look like CA:9.99 (country:price)")
            continue
        try:
            price, code = ps.parse_price(rest)
        except ValueError as exc:
            p.add(ERROR, "shipping-format", "shipping", f"shipping '{chunk}': {exc}")
            continue
        p.shipping.append(Shipping(country, price, code or p.currency))


def _returns(p: Product, v: dict[str, str]) -> None:
    if v.get("return_days"):
        try:
            p.return_days = ps.parse_return_days(v["return_days"])
        except ValueError as exc:
            p.add(ERROR, "return-days-format", "return_days", str(exc))
    if v.get("return_fees"):
        p.return_fees = ps.parse_return_fees(v["return_fees"]) or ""
        if not p.return_fees:
            p.add(ERROR, "return-fees-value", "return_fees",
                  f"return_fees '{v['return_fees']}' is not one of free, customer pays, restocking fee")
    if p.return_fees and p.return_days is None:
        p.add(WARNING, "return-days-missing", "return_days", "return_fees is given without return_days; the return policy is left out")


def check_duplicates(products: list[Product]) -> None:
    """Flag every repeated id after its first appearance (per language)."""
    first: dict[tuple[str, str], int] = {}
    for p in products:
        if not p.id:
            continue
        key = (p.lang, p.id)
        if key in first:
            p.add(ERROR, "id-duplicate", "id", f"id '{p.id}' was already used in row {first[key]}")
        else:
            first[key] = p.row


def detect_languages(table: Table, choice: str = "auto") -> list[str]:
    if choice == "auto":
        return table.languages()
    if choice not in LANG_TAGS:
        raise ValueError(f"unknown language '{choice}'; use auto, en or fr")
    return [choice]


def process(table: Table, options: Options | None = None, langs: list[str] | None = None) -> list[Product]:
    """Build and validate every row for every language, English products first."""
    options = options or Options()
    products: list[Product] = []
    for lang in langs or table.languages():
        batch = [build_product(row, lang, options) for row in table.rows]
        check_duplicates(batch)
        products.extend(batch)
    return products
