import datetime as dt
from decimal import Decimal

import pytest

from product_feed_gen.reader import parse_table
from product_feed_gen.validate import process


def codes(product, severity=None):
    return [i.code for i in product.issues if severity in (None, i.severity)]


def test_good_row_has_no_issues(make_product):
    p = make_product(product_type="Kitchen > Trays")
    assert p.issues == []
    assert (p.currency, p.price, p.availability, p.condition) == ("CAD", Decimal("19.99"), "in_stock", "new")


@pytest.mark.parametrize("field", ["id", "title", "description", "link", "image_link", "availability", "price", "brand"])
def test_each_required_attribute(make_product, field):
    p = make_product(**{field: ""})
    assert f"{field}-missing" in codes(p, "error")


def test_gtin_or_mpn_is_required(make_product):
    assert "identifier-missing" in codes(make_product(gtin=""), "error")
    assert "identifier-missing" not in codes(make_product(gtin="", mpn="OT-1"), "error")


@pytest.mark.parametrize("value", ["no", "No", "false", "non"])
def test_identifier_exists_no_waives_brand_gtin_mpn(make_product, value):
    p = make_product(gtin="", brand="", identifier_exists=value)
    assert codes(p, "error") == []
    assert "brand-missing-meta" in codes(p, "warning")  # Meta still wants a brand


def test_identifier_exists_conflict_and_bad_value(make_product):
    assert "identifier-conflict" in codes(make_product(identifier_exists="no"), "warning")
    assert "identifier-exists-value" in codes(make_product(identifier_exists="perhaps"), "error")


def test_invalid_gtin_is_an_error(make_product):
    assert "gtin-invalid" in codes(make_product(gtin="4006381333932"), "error")
    assert "gtin-invalid" not in codes(make_product(gtin="4006381333931"))


def test_condition_defaults_to_new_and_accepts_used(make_product):
    assert make_product().condition == "new"
    assert make_product(condition="Used").condition == "used"
    assert make_product(condition="refurbished").condition == "refurbished"
    assert "condition-value" in codes(make_product(condition="broken"), "error")


def test_availability_values(make_product):
    assert make_product(availability="in stock").availability == "in_stock"
    assert codes(make_product(availability="in stock"), "error") == []
    assert "availability-value" in codes(make_product(availability="soon"), "error")


@pytest.mark.parametrize("price", ["19.99", "$19.99", "19,99", "19.99 CAD"])
def test_price_formats(make_product, price):
    p = make_product(price=price)
    assert codes(p, "error") == []
    assert (p.price, p.currency) == (Decimal("19.99"), "CAD")


def test_price_errors(make_product):
    assert "price-format" in codes(make_product(price="cheap"), "error")
    assert "price-format" in codes(make_product(price="19.99 ZZZ"), "error")


def test_currency_rules(make_product, options):
    assert make_product(price="19.99").currency == "CAD"  # default
    assert make_product(price="19.99", currency="usd").currency == "USD"
    assert make_product(price="US$19.99").currency == "USD"
    assert "currency-value" in codes(make_product(currency="ZZZ"), "error")
    assert "currency-conflict" in codes(make_product(price="19.99 USD", currency="CAD"), "error")
    assert "currency-conflict" in codes(make_product(price="19.99 CAD", sale_price="9.99 USD"), "error")
    options.default_currency = "USD"
    assert make_product(price="19.99").currency == "USD"


def test_sale_price_must_be_lower(make_product):
    assert codes(make_product(sale_price="14.99"), "error") == []
    assert "sale-price-not-lower" in codes(make_product(sale_price="19.99"), "error")
    assert "sale-price-not-lower" in codes(make_product(sale_price="25"), "error")


def test_sale_window(make_product):
    p = make_product(sale_price="14.99", sale_price_effective_date="2026-09-01/2026-10-15")
    assert [i.code for i in p.issues if i.code.startswith("sale")] == []
    assert p.sale_start == "2026-09-01T00:00-05:00" and p.sale_end == "2026-10-15T23:59-05:00"
    p = make_product(sale_price="14.99", sale_start="2026-09-01", sale_end="2026-09-10")
    assert "sale-ended" in codes(p, "warning")
    bad_order = make_product(sale_price="14.99", sale_start="2026-10-01", sale_end="2026-09-01")
    assert "sale-window-order" in codes(bad_order, "error")
    assert "sale-date-format" in codes(make_product(sale_price="14.99", sale_start="soon"), "error")
    orphan = make_product(sale_start="2026-10-01", sale_end="2026-10-05")
    assert "sale-dates-without-price" in codes(orphan, "warning")


@pytest.mark.parametrize("field, value", [
    ("link", "http://shop.example.ca/p"),
    ("image_link", "http://shop.example.ca/i.jpg"),
    ("link", "shop.example.ca/p"),
    ("image_link", "ftp://shop.example.ca/i.jpg"),
])
def test_urls_must_be_https(make_product, field, value):
    assert f"{field}-url" in codes(make_product(**{field: value}), "error")


def test_allow_http_downgrades_to_warning(make_product, options):
    options.allow_http = True
    p = make_product(image_link="http://shop.example.ca/i.jpg")
    assert "image_link-url" in codes(p, "warning") and codes(p, "error") == []


def test_additional_images_checked(make_product):
    p = make_product(additional_image_links="https://shop.example.ca/a.jpg|http://shop.example.ca/b.jpg")
    assert p.additional_image_links == ["https://shop.example.ca/a.jpg", "http://shop.example.ca/b.jpg"]
    assert "additional-image-url" in codes(p, "error")
    many = "|".join(f"https://shop.example.ca/{i}.jpg" for i in range(11))
    assert "additional-images-count" in codes(make_product(additional_image_links=many), "error")


def test_title_and_description_limits(make_product):
    assert codes(make_product(title="x" * 150), "error") == []
    assert "title-too-long" in codes(make_product(title="x" * 151), "error")
    assert codes(make_product(description="x" * 5000), "error") == []
    assert "description-too-long" in codes(make_product(description="x" * 5001), "error")
    assert "id-too-long" in codes(make_product(id="x" * 51), "error")


def test_all_caps_title_warns(make_product):
    assert "title-all-caps" in codes(make_product(title="SOLID OAK SERVING TRAY"), "warning")


def test_duplicate_ids(fixtures):
    products = process(parse_table((fixtures / "invalid_products.csv").read_text(encoding="utf-8")))
    dupes = [p for p in products if "id-duplicate" in codes(p)]
    assert [p.row for p in dupes] == [7]
    assert "row 2" in next(i.message for i in dupes[0].issues if i.code == "id-duplicate")


def test_invalid_fixture_reports_each_problem(fixtures):
    products = process(parse_table((fixtures / "invalid_products.csv").read_text(encoding="utf-8")))
    by_row = {p.row: codes(p, "error") for p in products}
    assert by_row[2] == []
    assert by_row[3] == ["gtin-invalid"]
    assert by_row[4] == ["image_link-url"]
    assert by_row[5] == ["price-missing"]
    assert by_row[6] == ["sale-price-not-lower"]
    assert by_row[7] == ["id-duplicate"]
    assert by_row[8] == ["availability-value", "brand-missing"]


def test_valid_fixture_is_clean(fixtures):
    products = process(parse_table((fixtures / "valid_products.csv").read_text(encoding="utf-8")))
    assert [p.errors for p in products] == [[], [], []]
    assert products[1].condition == "used" and products[1].sale_price == Decimal("9.99")
    assert products[1].weight_unit == "g"


def test_shipping_weight_and_shipping(make_product):
    p = make_product(shipping_weight="1,5 kg", shipping="CA:9.99|US:20 USD")
    assert p.shipping_weight == "1.5 kg"
    got = [(s.country, str(s.price), s.currency) for s in p.shipping]
    assert got == [("CA", "9.99", "CAD"), ("US", "20.00", "USD")]
    assert "weight-unit-assumed" in codes(make_product(shipping_weight="2"), "warning")
    assert "shipping-weight-format" in codes(make_product(shipping_weight="heavy"), "error")
    assert "shipping-format" in codes(make_product(shipping="9.99"), "error")
    assert "shipping-format" in codes(make_product(shipping="CA:free"), "error")


def test_return_policy_fields(make_product):
    p = make_product(return_days="30 days", return_fees="Free returns")
    assert (p.return_days, p.return_fees) == (30, "free")
    assert "return-days-format" in codes(make_product(return_days="a month"), "error")
    assert "return-fees-value" in codes(make_product(return_fees="who knows"), "error")
    assert "return-days-missing" in codes(make_product(return_fees="free"), "warning")


def test_price_valid_until(make_product):
    assert make_product(price_valid_until="2026-12-31").price_valid_until == dt.date(2026, 12, 31)
    assert "price-valid-until-past" in codes(make_product(price_valid_until="2026-01-01"), "warning")
    assert "price-valid-until-format" in codes(make_product(price_valid_until="next year"), "error")


def test_missing_category_is_only_a_warning(make_product):
    assert "category-missing" in codes(make_product(), "warning")
    assert "category-missing" not in codes(make_product(product_type="Kitchen"))
    assert "category-missing" not in codes(make_product(google_product_category="Home & Garden"))
