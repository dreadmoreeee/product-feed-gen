import datetime as dt
from decimal import Decimal

import pytest

from product_feed_gen import parsing as ps


# ---- GTIN

@pytest.mark.parametrize("gtin", [
    "4006381333931",  # GTIN-13
    "036000291452",   # GTIN-12
    "96385074",       # GTIN-8
    "00012345678905",  # GTIN-14
    "4006 3813-33931",  # separators are tolerated
])
def test_valid_gtins(gtin):
    assert ps.check_gtin(gtin)[1] is None


@pytest.mark.parametrize("gtin, part", [
    ("4006381333932", "check digit"),
    ("036000291453", "check digit"),
    ("96385075", "check digit"),
    ("00012345678906", "check digit"),
    ("12345", "8, 12, 13 or 14"),
    ("400638133393123", "8, 12, 13 or 14"),
    ("40063813339X1", "digits only"),
])
def test_invalid_gtins(gtin, part):
    assert part in ps.check_gtin(gtin)[1]


def test_check_digit_reports_the_expected_value():
    assert "expected 1" in ps.check_gtin("4006381333932")[1]


# ---- prices

@pytest.mark.parametrize("text, amount, currency", [
    ("19.99 CAD", "19.99", "CAD"),
    ("CAD 19.99", "19.99", "CAD"),
    ("cad19.99", "19.99", "CAD"),
    ("$19.99", "19.99", None),
    ("19.99$", "19.99", None),
    ("19,99", "19.99", None),         # French decimal comma
    ("19,99 $", "19.99", None),
    ("24,5", "24.50", None),
    ("1 299,99 $", "1299.99", None),  # space as thousands separator
    ("1\u00a0299,99 $", "1299.99", None),  # non-breaking space
    ("1,299.99", "1299.99", None),
    ("1.299,99", "1299.99", None),
    ("1,299,000", "1299000.00", None),
    ("C$5", "5.00", "CAD"),
    ("CA$ 5.25", "5.25", "CAD"),
    ("US$5.50", "5.50", "USD"),
    ("5,50 $ US", "5.50", "USD"),
    ("5 usd", "5.00", "USD"),
    ("12", "12.00", None),
])
def test_parse_price(text, amount, currency):
    assert ps.parse_price(text) == (Decimal(amount), currency)


@pytest.mark.parametrize("text", [
    "", "abc", "free", "19.999", "0", "0.00", "19.99 XYZ", "CAD 19.99 USD",
    "1,299",  # ambiguous: 1.299 or 1299
    "19.99.99", "19 99",
])
def test_parse_price_rejects(text):
    with pytest.raises(ValueError):
        ps.parse_price(text)


def test_money_format():
    assert ps.money(Decimal("5"), "CAD") == "5.00 CAD"


# ---- enumerations

@pytest.mark.parametrize("text, expected", [
    ("in_stock", "in_stock"), ("in stock", "in_stock"), ("In Stock", "in_stock"),
    ("instock", "in_stock"), ("En stock", "in_stock"), ("available", "in_stock"),
    ("out_of_stock", "out_of_stock"), ("out of stock", "out_of_stock"), ("Sold out", "out_of_stock"),
    ("Rupture de stock", "out_of_stock"), ("\u00c9puis\u00e9", "out_of_stock"),
    ("preorder", "preorder"), ("pre-order", "preorder"), ("Pr\u00e9commande", "preorder"),
    ("backorder", "backorder"), ("back order", "backorder"), ("available for order", "backorder"),
    ("maybe", None), ("", None), ("in stock soon", None),
])
def test_availability_mapping(text, expected):
    assert ps.parse_availability(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("new", "new"), ("New", "new"), ("neuf", "new"),
    ("used", "used"), ("Pre-owned", "used"), ("d'occasion", "used"),
    ("refurbished", "refurbished"), ("Reconditionn\u00e9", "refurbished"),
    ("damaged", None),
])
def test_condition_mapping(text, expected):
    assert ps.parse_condition(text) == expected


def test_yes_no():
    assert ps.parse_yes_no("No") is False
    assert ps.parse_yes_no("oui") is True
    assert ps.parse_yes_no("perhaps") is None


# ---- dates, weight, urls

def test_parse_when_date_only_uses_offset_and_day_edges():
    assert ps.parse_when("2026-09-01", "-05:00") == ("2026-09-01T00:00-05:00", dt.date(2026, 9, 1))
    assert ps.parse_when("2026-09-01", "-05:00", end=True)[0] == "2026-09-01T23:59-05:00"


def test_parse_when_keeps_explicit_offset():
    assert ps.parse_when("2026-09-01T08:30:00-04:00", "-05:00")[0] == "2026-09-01T08:30-04:00"
    assert ps.parse_when("2026-09-01T08:30Z", "-05:00")[0] == "2026-09-01T08:30+00:00"


@pytest.mark.parametrize("text", ["tomorrow", "2026-13-01", "01/02/2026"])
def test_parse_when_rejects(text):
    with pytest.raises(ValueError):
        ps.parse_when(text, "-05:00")


def test_parse_weight():
    assert ps.parse_weight("1.5 kg") == (Decimal("1.5"), "kg", False)
    assert ps.parse_weight("500G") == (Decimal("500"), "g", False)
    assert ps.parse_weight("2 lbs")[1] == "lb"
    assert ps.parse_weight("0,5") == (Decimal("0.5"), "kg", True)
    with pytest.raises(ValueError):
        ps.parse_weight("heavy")


def test_check_url():
    assert ps.check_url("https://shop.example.ca/a", False) is None
    assert ps.check_url("http://shop.example.ca/a", False)[0] == "error"
    assert ps.check_url("http://shop.example.ca/a", True)[0] == "warning"
    assert ps.check_url("ftp://shop.example.ca/a", False)[0] == "error"
    assert ps.check_url("shop.example.ca/a", False)[0] == "error"
    assert ps.check_url("https://shop.example.ca/a b", False)[0] == "error"


def test_split_list_keeps_commas_inside_urls():
    text = "https://x.example.ca/a?s=1,2, https://x.example.ca/b|https://x.example.ca/c"
    assert ps.split_list(text) == ["https://x.example.ca/a?s=1,2", "https://x.example.ca/b", "https://x.example.ca/c"]
