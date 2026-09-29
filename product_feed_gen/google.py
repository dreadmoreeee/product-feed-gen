"""Google Merchant Center product feed (RSS 2.0 with the g: namespace)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .model import Product
from .parsing import money

G_NS = "http://base.google.com/ns/1.0"
ET.register_namespace("g", G_NS)

_BAD_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _clean(text: str) -> str:
    """Drop characters that are not allowed in XML 1.0 (they would break the file)."""
    return _BAD_XML_CHARS.sub("", text)


def _g(parent: ET.Element, name: str, text: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{G_NS}}}{name}")
    el.text = _clean(text)
    return el


def _item(p: Product) -> ET.Element:
    item = ET.Element("item")
    _g(item, "id", p.id)
    _g(item, "title", p.title)
    _g(item, "description", p.description)
    _g(item, "link", p.link)
    _g(item, "image_link", p.image_link)
    for url in p.additional_image_links:
        _g(item, "additional_image_link", url)
    if p.availability:
        _g(item, "availability", p.availability)
    if p.price is not None:
        _g(item, "price", money(p.price, p.currency))
    if p.sale_price is not None:
        _g(item, "sale_price", money(p.sale_price, p.currency))
        if p.sale_start and p.sale_end:
            _g(item, "sale_price_effective_date", f"{p.sale_start}/{p.sale_end}")
    _g(item, "condition", p.condition)
    if p.brand:
        _g(item, "brand", p.brand)
    if p.gtin:
        _g(item, "gtin", p.gtin)
    if p.mpn:
        _g(item, "mpn", p.mpn)
    if p.identifier_exists is False:
        _g(item, "identifier_exists", "no")
    if p.google_product_category:
        _g(item, "google_product_category", p.google_product_category)
    if p.product_type:
        _g(item, "product_type", p.product_type)
    if p.weight_value is not None:
        _g(item, "shipping_weight", p.shipping_weight)
    for s in p.shipping:
        ship = ET.SubElement(item, f"{{{G_NS}}}shipping")
        _g(ship, "country", s.country)
        _g(ship, "price", money(s.price, s.currency))
    return item


def render_google_feed(
    products: list[Product],
    lang_tag: str = "en-CA",
    shop_name: str = "Product feed",
    shop_url: str = "",
    shop_description: str = "",
) -> str:
    """Return the feed as an XML string (UTF-8 declaration included)."""
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = _clean(shop_name)
    ET.SubElement(channel, "link").text = _clean(shop_url)
    ET.SubElement(channel, "description").text = _clean(shop_description or shop_name)
    ET.SubElement(channel, "language").text = lang_tag
    for p in products:
        channel.append(_item(p))
    ET.indent(rss, space="  ")
    body = ET.tostring(rss, encoding="unicode")
    if "xmlns:g=" not in body:  # an empty feed uses no g: element, keep the declaration anyway
        body = body.replace('<rss version="2.0"', f'<rss xmlns:g="{G_NS}" version="2.0"', 1)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
