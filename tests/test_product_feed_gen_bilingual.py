import csv
import io
import xml.etree.ElementTree as ET

from product_feed_gen.cli import main
from product_feed_gen.google import G_NS, render_google_feed
from product_feed_gen.meta import render_meta_csv
from product_feed_gen.reader import read_table
from product_feed_gen.validate import detect_languages, process

G = "{" + G_NS + "}"


def test_two_languages_are_produced(fixtures, options):
    table = read_table(fixtures / "bilingual.csv")
    assert detect_languages(table) == ["en", "fr"]
    products = process(table, options)
    assert [(p.tag, p.id) for p in products] == [("en-CA", "B-1"), ("en-CA", "B-2"), ("fr-CA", "B-1"), ("fr-CA", "B-2")]
    en, fr = products[0], products[2]
    assert (en.title, fr.title) == ("Maple Board", "Planche en \u00e9rable")
    assert (en.link, fr.link) == ("https://shop.example.ca/en/b-1", "https://shop.example.ca/fr/b-1")
    assert fr.description == "Planche en \u00e9rable massif."


def test_french_decimal_comma_price_is_read_in_both_languages(fixtures, options):
    products = process(read_table(fixtures / "bilingual.csv"), options)
    assert [str(p.price) for p in products if p.id == "B-2"] == ["24.00", "24.00"]


def test_missing_translation_is_an_error_when_there_is_no_base_column(fixtures, options):
    products = process(read_table(fixtures / "bilingual.csv"), options)
    fr_b2 = products[3]
    codes = [i.code for i in fr_b2.errors]
    assert codes == ["title-missing", "description-missing"]
    assert [i.code for i in products[1].errors] == []  # English side is fine


def test_blank_translation_falls_back_to_the_base_column(options):
    from product_feed_gen.reader import parse_table
    text = (
        "id,title,title_fr,description,link,image_link,price,availability,brand,mpn\n"
        "X-1,Oak Tray,,Solid oak.,https://shop.example.ca/x,https://shop.example.ca/x.jpg,10,in stock,Example,M-1\n"
    )
    products = process(parse_table(text), options)
    fr = [p for p in products if p.lang == "fr"][0]
    assert fr.title == "Oak Tray"
    assert [i.code for i in fr.warnings] == ["lang-fallback", "category-missing"]
    assert fr.errors == []


def test_each_language_gets_its_own_feed(fixtures, options):
    products = process(read_table(fixtures / "bilingual.csv"), options)
    feeds = {}
    for tag in ("en-CA", "fr-CA"):
        batch = [p for p in products if p.tag == tag and not p.errors]
        root = ET.fromstring(render_google_feed(batch, tag).encode("utf-8"))
        assert root.findtext("channel/language") == tag
        feeds[tag] = root.findall("channel/item")
    assert [i.findtext(G + "title") for i in feeds["en-CA"]] == ["Maple Board", "Cedar Box"]
    assert [i.findtext(G + "title") for i in feeds["fr-CA"]] == ["Planche en \u00e9rable"]  # B-2 has no French text
    assert feeds["fr-CA"][0].findtext(G + "link").endswith("/fr/b-1")


def test_meta_csv_per_language(fixtures, options):
    products = process(read_table(fixtures / "bilingual.csv"), options)
    fr = [p for p in products if p.tag == "fr-CA" and not p.errors]
    rows = list(csv.DictReader(io.StringIO(render_meta_csv(fr))))
    assert [r["title"] for r in rows] == ["Planche en \u00e9rable"]
    assert rows[0]["availability"] == "in stock"


def test_single_language_csv_yields_en_ca_only(fixtures, options):
    products = process(read_table(fixtures / "valid_products.csv"), options)
    assert {p.tag for p in products} == {"en-CA"}


def test_cli_writes_language_flag_in_file_names(fixtures, tmp_path, capsys):
    out = tmp_path / "out"
    assert main([str(fixtures / "bilingual.csv"), "--out", str(out), "--today", "2026-09-29"]) == 0
    names = sorted(p.name for p in out.iterdir())
    assert names == [
        "google-feed.en-CA.xml", "google-feed.fr-CA.xml",
        "jsonld.en-CA.html", "jsonld.en-CA.json", "jsonld.fr-CA.html", "jsonld.fr-CA.json",
        "meta-catalog.en-CA.csv", "meta-catalog.fr-CA.csv", "report.txt",
    ]
    fr = ET.parse(out / "google-feed.fr-CA.xml").getroot()
    assert fr.findtext("channel/language") == "fr-CA"


def test_cli_lang_option_limits_output(fixtures, tmp_path):
    out = tmp_path / "out"
    assert main([str(fixtures / "bilingual.csv"), "--out", str(out), "--lang", "fr", "--formats", "google"]) == 0
    assert [p.name for p in out.iterdir() if p.suffix == ".xml"] == ["google-feed.fr-CA.xml"]
