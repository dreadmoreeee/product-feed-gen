import pytest

from product_feed_gen.reader import ReaderError, parse_table, read_table
from product_feed_gen.validate import process


def test_tolerant_header_names(fixtures):
    table = read_table(fixtures / "valid_products.csv")
    assert table.columns["id"] == "SKU"
    assert table.columns["title"] == "Product Name"
    assert table.columns["availability"] == "Stock Status"
    assert table.columns["image_link"] == "Image"
    assert table.columns["link"] == "URL"
    assert table.columns["additional_image_links"] == "Additional Images"
    assert table.columns["product_type"] == "Category"
    assert table.unmapped == []
    assert [r.number for r in table.rows] == [2, 3, 4]


def test_headers_ignore_case_accents_and_google_prefix():
    table = parse_table("G:ID, TITRE ,Prix R\u00e9gulier,g:image_link\nx,y,1,z\n")
    assert set(table.columns) == {"id", "title", "price", "image_link"}


def test_exact_canonical_header_beats_alias():
    table = parse_table("name,title,id\nalias,exact,1\n")
    assert table.columns["title"] == "title"
    assert table.unmapped == ["name"]
    assert table.rows[0].values["title"] == "exact"


def test_semicolon_delimiter_and_french_headers(fixtures):
    table = read_table(fixtures / "semicolon_fr.csv")
    expected = {"id", "title", "description", "price", "currency", "availability", "brand", "mpn", "image_link", "link"}
    assert set(table.columns) >= expected
    products = process(table)
    assert [str(p.price) for p in products] == ["1299.99", "12.50"]
    assert [p.availability for p in products] == ["in_stock", "out_of_stock"]
    assert all(not p.errors for p in products)


def test_windows_1252_file_is_decoded(tmp_path):
    path = tmp_path / "excel.csv"
    path.write_bytes("id;titre\nA;Cr\u00e8me br\u00fbl\u00e9e\n".encode("cp1252"))
    table = read_table(path)
    assert table.encoding == "cp1252"
    assert table.rows[0].values["title"] == "Cr\u00e8me br\u00fbl\u00e9e"


def test_utf8_bom_is_removed(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(b"\xef\xbb\xbfid,title\nA,B\n")
    assert read_table(path).columns["id"] == "id"


def test_blank_rows_skipped_but_row_numbers_kept():
    table = parse_table("id,title\nA,one\n,\n\nB,two\n")
    assert [(r.number, r.values["id"]) for r in table.rows] == [(2, "A"), (5, "B")]


def test_short_rows_are_padded():
    table = parse_table("id,title,price\nA,one\n")
    assert table.rows[0].values["price"] == ""


def test_explicit_mapping(fixtures):
    mapping = {"id": "Item Code", "title": "Label", "description": "Long text",
               "price": "regular price eur", "image_link": "Picture", "link": "Page"}
    table = read_table(fixtures / "custom_headers.csv", mapping)
    assert table.columns["brand"] == "Vendor"
    product = process(table)[0]
    assert (product.id, product.title, str(product.price)) == ("C-1", "Custom one", "15.00")
    assert product.image_link.endswith("c1.jpg")


def test_without_mapping_custom_headers_stay_unmapped(fixtures):
    table = read_table(fixtures / "custom_headers.csv")
    assert "Item Code" in table.unmapped and "Label" in table.unmapped


def test_mapping_errors():
    with pytest.raises(ReaderError, match="not in the CSV header"):
        parse_table("id,title\nA,B\n", {"price": "Cost"})
    with pytest.raises(ReaderError, match="unknown field"):
        parse_table("id,title\nA,B\n", {"colour": "id"})


def test_empty_and_missing_files(tmp_path):
    with pytest.raises(ReaderError):
        parse_table("")
    with pytest.raises(ReaderError):
        read_table(tmp_path / "nope.csv")


def test_language_columns_detected():
    assert parse_table("id,title_en,title_fr\n").languages() == ["en", "fr"]
    assert parse_table("id,title_en,link_en_ca\n").languages() == ["en"]
    assert parse_table("id,title\n").languages() == ["en"]
    assert parse_table("id,titre_fr\n").languages() == ["fr"]
