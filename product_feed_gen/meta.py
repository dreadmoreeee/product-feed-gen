"""Meta (Facebook / Instagram) catalog CSV."""
from __future__ import annotations

import csv
import io

from .model import Product
from .parsing import money

COLUMNS = [
    "id", "title", "description", "availability", "condition", "price", "link", "image_link",
    "brand", "sale_price", "sale_price_effective_date", "additional_image_link", "gtin", "mpn",
    "google_product_category", "product_type", "shipping", "shipping_weight",
]

# Meta spells some availability values differently from Google.
AVAILABILITY = {
    "in_stock": "in stock",
    "out_of_stock": "out of stock",
    "preorder": "preorder",
    "backorder": "available for order",
}


def meta_row(p: Product) -> dict[str, str]:
    window = f"{p.sale_start}/{p.sale_end}" if p.sale_start and p.sale_end else ""
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "availability": AVAILABILITY.get(p.availability, ""),
        "condition": p.condition,
        "price": money(p.price, p.currency) if p.price is not None else "",
        "link": p.link,
        "image_link": p.image_link,
        "brand": p.brand,
        "sale_price": money(p.sale_price, p.currency) if p.sale_price is not None else "",
        "sale_price_effective_date": window if p.sale_price is not None else "",
        "additional_image_link": ",".join(p.additional_image_links),
        "gtin": p.gtin,
        "mpn": p.mpn,
        "google_product_category": p.google_product_category,
        "product_type": p.product_type,
        # Meta wants Country:Region:Service:Price; region and service are left empty
        "shipping": ",".join(f"{s.country}:::{money(s.price, s.currency)}" for s in p.shipping),
        "shipping_weight": p.shipping_weight,
    }


def render_meta_csv(products: list[Product]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for p in products:
        writer.writerow(meta_row(p))
    return out.getvalue()
