"""schema.org Product + Offer JSON-LD, one object per product."""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

from .model import Product

SCHEMA = "https://schema.org/"
AVAILABILITY = {
    "in_stock": "InStock",
    "out_of_stock": "OutOfStock",
    "preorder": "PreOrder",
    "backorder": "BackOrder",
}
CONDITION = {"new": "NewCondition", "used": "UsedCondition", "refurbished": "RefurbishedCondition"}
RETURN_FEES = {"free": "FreeReturn", "customer_pays": "ReturnShippingFees", "restocking": "RestockingFees"}
WEIGHT_UNITS = {"kg": "KGM", "g": "GRM", "lb": "LBR", "oz": "ONZ"}


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _return_policy(p: Product) -> dict | None:
    if p.return_days is None:
        return None
    policy: dict = {"@type": "MerchantReturnPolicy", "applicableCountry": p.return_country}
    if p.return_days == 0:
        policy["returnPolicyCategory"] = SCHEMA + "MerchantReturnNotPermitted"
        return policy
    policy["returnPolicyCategory"] = SCHEMA + "MerchantReturnFiniteReturnWindow"
    policy["merchantReturnDays"] = p.return_days
    if p.return_fees:
        policy["returnFees"] = SCHEMA + RETURN_FEES[p.return_fees]
    return policy


def _offer(p: Product, today: dt.date) -> dict:
    on_sale = p.sale_is_active(today)
    offer: dict = {"@type": "Offer", "url": p.link}
    price = p.sale_price if on_sale else p.price
    if price is not None:
        offer["priceCurrency"] = p.currency
        offer["price"] = _amount(price)
    if on_sale and p.price is not None:
        offer["priceSpecification"] = [{
            "@type": "UnitPriceSpecification",
            "priceType": SCHEMA + "ListPrice",
            "price": _amount(p.price),
            "priceCurrency": p.currency,
        }]
    valid_until = p.price_valid_until or (p.sale_end_date if on_sale else None)
    if valid_until:
        offer["priceValidUntil"] = valid_until.isoformat()
    if p.availability:
        offer["availability"] = SCHEMA + AVAILABILITY[p.availability]
    offer["itemCondition"] = SCHEMA + CONDITION[p.condition]
    if p.shipping:
        details = [{
            "@type": "OfferShippingDetails",
            "shippingRate": {"@type": "MonetaryAmount", "value": _amount(s.price), "currency": s.currency},
            "shippingDestination": {"@type": "DefinedRegion", "addressCountry": s.country},
        } for s in p.shipping]
        offer["shippingDetails"] = details[0] if len(details) == 1 else details
    policy = _return_policy(p)
    if policy:
        offer["hasMerchantReturnPolicy"] = policy
    return offer


def product_jsonld(p: Product, today: dt.date | None = None) -> dict:
    """The schema.org Product for one product; optional parts only when the data exists."""
    today = today or dt.date.today()
    data: dict = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": p.title,
        "description": p.description,
        "sku": p.id,
    }
    images = [u for u in [p.image_link, *p.additional_image_links] if u]
    if images:
        data["image"] = images[0] if len(images) == 1 else images
    if p.brand:
        data["brand"] = {"@type": "Brand", "name": p.brand}
    if p.gtin:
        data[f"gtin{len(p.gtin)}"] = p.gtin
    if p.mpn:
        data["mpn"] = p.mpn
    if p.category:
        data["category"] = p.category
    if p.weight_value is not None:
        data["weight"] = {
            "@type": "QuantitativeValue",
            "value": float(p.weight_value),
            "unitCode": WEIGHT_UNITS[p.weight_unit],
        }
    data["offers"] = _offer(p, today)
    return data


def render_jsonld_json(products: list[Product], today: dt.date | None = None) -> str:
    return json.dumps([product_jsonld(p, today) for p in products], indent=2, ensure_ascii=False) + "\n"


def render_jsonld_html(products: list[Product], today: dt.date | None = None) -> str:
    """One <script type="application/ld+json"> block per product, ready to paste in a page."""
    blocks = []
    for p in products:
        body = json.dumps(product_jsonld(p, today), indent=2, ensure_ascii=False)
        body = body.replace("</", "<\\/")  # a value can never close the script element
        label = p.id.replace("--", "- -").replace(">", "")
        blocks.append(f"<!-- {label} -->\n<script type=\"application/ld+json\">\n{body}\n</script>\n")
    return "\n".join(blocks)
