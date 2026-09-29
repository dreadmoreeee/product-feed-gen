import csv
import datetime as dt
import io
import json
import re
import xml.etree.ElementTree as ET

import pytest

from product_feed_gen import meta
from product_feed_gen.google import G_NS, render_google_feed
from product_feed_gen.jsonld import product_jsonld, render_jsonld_html, render_jsonld_json
from product_feed_gen.meta import render_meta_csv
from product_feed_gen.reader import parse_table
from product_feed_gen.validate import process

G = "{" + G_NS + "}"
TODAY = dt.date(2026, 9, 29)


def valid_products(fixtures):
    return process(parse_table((fixtures / "valid_products.csv").read_text(encoding="utf-8")))


# ---- Google XML

def test_google_feed_parses_back(fixtures):
    products = valid_products(fixtures)
    text = render_google_feed(products, "en-CA", "Example Shop", "https://shop.example.ca/", "Demo")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(text.encode("utf-8"))
    assert root.tag == "rss" and root.get("version") == "2.0"
    assert 'xmlns:g="http://base.google.com/ns/1.0"' in text
    channel = root.find("channel")
    assert channel.findtext("title") == "Example Shop"
    assert channel.findtext("language") == "en-CA"
    items = channel.findall("item")
    assert [i.findtext(G + "id") for i in items] == ["A-100", "A-101", "A-102"]
    first = items[0]
    assert first.findtext(G + "price") == "19.99 CAD"
    assert first.findtext(G + "availability") == "in_stock"
    assert first.findtext(G + "condition") == "new"
    assert first.findtext(G + "gtin") == "4006381333931"
    assert first.findtext(G + "shipping_weight") == "1.5 kg"
    second = items[1]
    assert second.findtext(G + "sale_price") == "9.99 CAD"
    assert [e.text for e in second.findall(G + "additional_image_link")] == [
        "https://shop.example.ca/i/a-101-b.jpg", "https://shop.example.ca/i/a-101-c.jpg"]
    assert second.findtext(G + "condition") == "used"
    assert second.find(G + "gtin") is None


def test_google_feed_escapes_special_characters(make_product):
    p = make_product(title='Tom & Jerry <"big"> tray', description="5 < 6 & 7 > 3", link="https://shop.example.ca/p?a=1&b=2")
    text = render_google_feed([p])
    assert "&amp;" in text and "&lt;" in text
    item = ET.fromstring(text.encode("utf-8")).find("channel/item")
    assert item.findtext(G + "title") == 'Tom & Jerry <"big"> tray'
    assert item.findtext(G + "description") == "5 < 6 & 7 > 3"
    assert item.findtext(G + "link") == "https://shop.example.ca/p?a=1&b=2"


def test_google_feed_drops_characters_xml_cannot_hold(make_product):
    p = make_product(description="bell\x07 and null\x00 removed")
    item = ET.fromstring(render_google_feed([p]).encode("utf-8")).find("channel/item")
    assert item.findtext(G + "description") == "bell and null removed"


def test_google_feed_keeps_accents(make_product):
    p = make_product(title="Planche \u00e0 d\u00e9couper")
    item = ET.fromstring(render_google_feed([p]).encode("utf-8")).find("channel/item")
    assert item.findtext(G + "title") == "Planche \u00e0 d\u00e9couper"


def test_empty_google_feed_is_still_valid_and_declares_namespace():
    text = render_google_feed([])
    root = ET.fromstring(text.encode("utf-8"))
    assert root.find("channel/item") is None
    assert 'xmlns:g="http://base.google.com/ns/1.0"' in text


def test_google_feed_identifier_exists_and_shipping(make_product):
    p = make_product(gtin="", brand="", identifier_exists="no", shipping="CA:9.99|US:20 USD")
    item = ET.fromstring(render_google_feed([p]).encode("utf-8")).find("channel/item")
    assert item.findtext(G + "identifier_exists") == "no"
    assert item.find(G + "brand") is None
    ships = item.findall(G + "shipping")
    assert [(s.findtext(G + "country"), s.findtext(G + "price")) for s in ships] == [("CA", "9.99 CAD"), ("US", "20.00 USD")]


def test_google_sale_window_uses_offset(make_product):
    p = make_product(sale_price="9.99", sale_price_effective_date="2026-09-01/2026-10-15")
    item = ET.fromstring(render_google_feed([p]).encode("utf-8")).find("channel/item")
    assert item.findtext(G + "sale_price_effective_date") == "2026-09-01T00:00-05:00/2026-10-15T23:59-05:00"


# ---- Meta CSV

def test_meta_csv_columns_and_rows(fixtures):
    text = render_meta_csv(valid_products(fixtures))
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == meta.COLUMNS
    for required in ("id", "title", "description", "availability", "condition", "price", "link", "image_link", "brand", "sale_price"):
        assert required in reader.fieldnames
    rows = list(reader)
    assert [r["id"] for r in rows] == ["A-100", "A-101", "A-102"]
    assert rows[0]["price"] == "19.99 CAD"
    assert rows[0]["availability"] == "in stock"
    assert rows[1]["availability"] == "out of stock"
    assert rows[2]["availability"] == "preorder"
    assert rows[1]["sale_price"] == "9.99 CAD" and rows[0]["sale_price"] == ""
    assert rows[1]["condition"] == "used"
    assert rows[1]["additional_image_link"] == "https://shop.example.ca/i/a-101-b.jpg,https://shop.example.ca/i/a-101-c.jpg"
    assert rows[0]["shipping_weight"] == "1.5 kg"


def test_meta_backorder_and_shipping(make_product):
    p = make_product(availability="back order", shipping="CA:9.99")
    row = next(csv.DictReader(io.StringIO(render_meta_csv([p]))))
    assert row["availability"] == "available for order"
    assert row["shipping"] == "CA:::9.99 CAD"


def test_meta_csv_quotes_commas_and_newlines(make_product):
    p = make_product(title="Tray, large", description="Line one\nLine two, \"quoted\"")
    row = next(csv.DictReader(io.StringIO(render_meta_csv([p]))))
    assert row["title"] == "Tray, large"
    assert row["description"] == "Line one\nLine two, \"quoted\""


# ---- JSON-LD

def test_jsonld_product_and_offer(make_product):
    p = make_product(condition="refurbished", additional_image_links="https://shop.example.ca/i/2.jpg",
                     mpn="OT-1", shipping_weight="1.5 kg", google_product_category="Home & Garden")
    data = product_jsonld(p, TODAY)
    assert data["@context"] == "https://schema.org" and data["@type"] == "Product"
    assert data["name"] == "Oak Tray" and data["sku"] == "T-1" and data["mpn"] == "OT-1"
    assert data["gtin13"] == "4006381333931"
    assert data["brand"] == {"@type": "Brand", "name": "Example Wood Co"}
    assert data["image"] == ["https://shop.example.ca/i/t-1.jpg", "https://shop.example.ca/i/2.jpg"]
    assert data["weight"] == {"@type": "QuantitativeValue", "value": 1.5, "unitCode": "KGM"}
    assert data["category"] == "Home & Garden"
    offer = data["offers"]
    assert offer["@type"] == "Offer"
    assert offer["price"] == "19.99" and offer["priceCurrency"] == "CAD"
    assert offer["url"] == "https://shop.example.ca/p/t-1"
    assert offer["availability"] == "https://schema.org/InStock"
    assert offer["itemCondition"] == "https://schema.org/RefurbishedCondition"


@pytest.mark.parametrize("availability, expected", [
    ("in_stock", "InStock"), ("out_of_stock", "OutOfStock"), ("preorder", "PreOrder"), ("backorder", "BackOrder"),
])
def test_jsonld_availability_urls(make_product, availability, expected):
    offer = product_jsonld(make_product(availability=availability), TODAY)["offers"]
    assert offer["availability"] == "https://schema.org/" + expected


def test_jsonld_optional_parts_only_when_data_is_given(make_product):
    offer = product_jsonld(make_product(), TODAY)["offers"]
    for key in ("priceValidUntil", "shippingDetails", "hasMerchantReturnPolicy", "priceSpecification"):
        assert key not in offer
    data = product_jsonld(make_product(gtin="", identifier_exists="no", brand=""), TODAY)
    for key in ("gtin13", "mpn", "brand", "weight", "category"):
        assert key not in data


def test_jsonld_price_valid_until_shipping_and_return_policy(make_product):
    p = make_product(price_valid_until="2026-12-31", shipping="CA:9.99", return_days="30", return_fees="free")
    offer = product_jsonld(p, TODAY)["offers"]
    assert offer["priceValidUntil"] == "2026-12-31"
    assert offer["shippingDetails"] == {
        "@type": "OfferShippingDetails",
        "shippingRate": {"@type": "MonetaryAmount", "value": "9.99", "currency": "CAD"},
        "shippingDestination": {"@type": "DefinedRegion", "addressCountry": "CA"},
    }
    assert offer["hasMerchantReturnPolicy"] == {
        "@type": "MerchantReturnPolicy",
        "applicableCountry": "CA",
        "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
        "merchantReturnDays": 30,
        "returnFees": "https://schema.org/FreeReturn",
    }


def test_jsonld_several_shipping_rates_become_a_list(make_product):
    offer = product_jsonld(make_product(shipping="CA:9.99|US:20 USD"), TODAY)["offers"]
    assert [d["shippingDestination"]["addressCountry"] for d in offer["shippingDetails"]] == ["CA", "US"]


def test_jsonld_return_not_permitted_and_fees(make_product):
    zero = product_jsonld(make_product(return_days="0"), TODAY)["offers"]["hasMerchantReturnPolicy"]
    assert zero["returnPolicyCategory"] == "https://schema.org/MerchantReturnNotPermitted"
    assert "merchantReturnDays" not in zero
    paid = product_jsonld(make_product(return_days="14", return_fees="restocking fee"), TODAY)["offers"]
    assert paid["hasMerchantReturnPolicy"]["returnFees"] == "https://schema.org/RestockingFees"


def test_jsonld_sale_active_and_expired(make_product):
    active = product_jsonld(make_product(sale_price="14.99", sale_start="2026-09-01", sale_end="2026-10-15"), TODAY)["offers"]
    assert active["price"] == "14.99"
    assert active["priceSpecification"][0]["price"] == "19.99"
    assert active["priceSpecification"][0]["priceType"] == "https://schema.org/ListPrice"
    assert active["priceValidUntil"] == "2026-10-15"
    expired = product_jsonld(make_product(sale_price="14.99", sale_start="2026-08-01", sale_end="2026-08-31"), TODAY)["offers"]
    assert expired["price"] == "19.99" and "priceSpecification" not in expired
    future = product_jsonld(make_product(sale_price="14.99", sale_start="2026-11-01", sale_end="2026-11-30"), TODAY)["offers"]
    assert future["price"] == "19.99"


def test_jsonld_file_is_a_json_array(fixtures):
    data = json.loads(render_jsonld_json(valid_products(fixtures), TODAY))
    assert [d["sku"] for d in data] == ["A-100", "A-101", "A-102"]
    assert all(d["@type"] == "Product" and d["offers"]["@type"] == "Offer" for d in data)


def test_jsonld_html_blocks_parse(fixtures, make_product):
    products = valid_products(fixtures) + [make_product(description="</script><b>x</b>")]
    html = render_jsonld_html(products, TODAY)
    blocks = re.findall(r'<script type="application/ld\+json">\n(.*?)\n</script>', html, re.S)
    assert len(blocks) == 4
    parsed = [json.loads(b) for b in blocks]
    assert parsed[0]["sku"] == "A-100"
    assert parsed[3]["description"] == "</script><b>x</b>"  # round-trips, yet cannot close the tag
    assert html.count("</script>") == 4
