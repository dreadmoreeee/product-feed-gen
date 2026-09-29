import csv
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

from product_feed_gen.cli import main

G = "{http://base.google.com/ns/1.0}"


def run(args, capsys):
    code = main([str(a) for a in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_clean_file_exits_zero_even_with_strict(fixtures, capsys):
    code, out, _ = run([fixtures / "valid_products.csv", "--strict"], capsys)
    assert code == 0
    assert "en-CA: " not in out  # one language: no language prefix
    assert "3 products: 3 ok, 0 with warnings only, 0 with errors" in out


def test_errors_exit_zero_without_strict_and_one_with_strict(fixtures, capsys):
    assert run([fixtures / "invalid_products.csv"], capsys)[0] == 0
    code, out, _ = run([fixtures / "invalid_products.csv", "--strict"], capsys)
    assert code == 1
    assert "gtin-invalid" in out and "price-missing" in out


def test_warnings_alone_do_not_fail_strict(tmp_path, capsys):
    path = tmp_path / "warn.csv"
    path.write_text(
        "id,title,description,price,availability,brand,mpn,image_link,link\n"
        "W-1,Tray,A tray.,10,in stock,Example,M-1,https://shop.example.ca/i.jpg,https://shop.example.ca/p\n",
        encoding="utf-8")
    code, out, _ = run([path, "--strict"], capsys)
    assert code == 0 and "category-missing" in out and "ERROR" not in out


def test_usage_errors_exit_two(fixtures, tmp_path, capsys):
    assert run([tmp_path / "missing.csv"], capsys)[0] == 2
    assert run([fixtures / "valid_products.csv", "--map", "price=Nope"], capsys)[0] == 2
    assert run([fixtures / "valid_products.csv", "--map", "oops"], capsys)[0] == 2
    assert run([fixtures / "valid_products.csv", "--formats", "pdf"], capsys)[0] == 2
    assert run([fixtures / "valid_products.csv", "--tz-offset", "EST"], capsys)[0] == 2
    assert run([fixtures / "valid_products.csv", "--today", "yesterday"], capsys)[0] == 2
    assert run([fixtures / "valid_products.csv", "--currency", "ZZZ"], capsys)[0] == 2
    header_only = tmp_path / "empty.csv"
    header_only.write_text("id,title\n", encoding="utf-8")
    assert run([header_only], capsys)[0] == 2


def test_invalid_products_are_left_out_of_feeds(fixtures, tmp_path, capsys):
    out = tmp_path / "out"
    run([fixtures / "invalid_products.csv", "--out", out, "--formats", "google,meta"], capsys)
    ids = [i.findtext(G + "id") for i in ET.parse(out / "google-feed.en-CA.xml").getroot().findall("channel/item")]
    assert ids == ["OK-1"]
    rows = list(csv.DictReader((out / "meta-catalog.en-CA.csv").open(encoding="utf-8")))
    assert [r["id"] for r in rows] == ["OK-1"]


def test_include_invalid_keeps_them(fixtures, tmp_path, capsys):
    out = tmp_path / "out"
    code, text, _ = run([fixtures / "invalid_products.csv", "--out", out, "--formats", "google", "--include-invalid"], capsys)
    assert code == 0
    ids = [i.findtext(G + "id") for i in ET.parse(out / "google-feed.en-CA.xml").getroot().findall("channel/item")]
    assert len(ids) == 7
    assert "are kept in the feeds" in text


def test_report_formats(fixtures, capsys):
    _, text, _ = run([fixtures / "invalid_products.csv", "--report", "json"], capsys)
    data = json.loads(text)
    assert data["summary"]["en-CA"] == {"products": 7, "ok": 0, "warning": 1, "error": 6}
    bad = [p for p in data["products"] if p["id"] == "BAD-GTIN"][0]
    assert bad["status"] == "error" and bad["issues"][0]["code"] == "gtin-invalid"
    _, md, _ = run([fixtures / "invalid_products.csv", "--report", "markdown"], capsys)
    assert md.startswith("# Product feed report") and "| Row | ID | Severity | Field | Problem |" in md


def test_report_file_and_out_dir_report(fixtures, tmp_path, capsys):
    target = tmp_path / "r.md"
    code, out, err = run([fixtures / "invalid_products.csv", "--report", "markdown", "--report-file", target], capsys)
    assert out == "" and target.read_text(encoding="utf-8").startswith("# Product feed report")
    out_dir = tmp_path / "o"
    run([fixtures / "invalid_products.csv", "--report", "json", "--out", out_dir], capsys)
    assert json.loads((out_dir / "report.json").read_text(encoding="utf-8"))["source"] == "invalid_products.csv"


def test_column_mapping_from_cli_and_file(fixtures, tmp_path, capsys):
    args = ["--map", "id=Item Code", "--map", "title=Label", "--map", "description=Long text",
            "--map", "price=Regular price EUR", "--map", "image_link=Picture", "--map", "link=Page"]
    code, out, _ = run([fixtures / "custom_headers.csv", "--strict", "--currency", "EUR", *args], capsys)
    assert code == 1 and "identifier-missing" in out  # mapped fine; the row has no gtin or mpn
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"id": "Item Code", "title": "Label", "description": "Long text",
                                   "price": "Regular price EUR", "image_link": "Picture", "link": "Page"}), encoding="utf-8")
    code, out, _ = run([fixtures / "custom_headers.csv", "--mapping", mapping, "--strict"], capsys)
    assert code == 1 and "price-missing" not in out


def test_default_shop_url_and_currency_option(fixtures, tmp_path, capsys):
    out = tmp_path / "o"
    run([fixtures / "custom_headers.csv", "--out", out, "--include-invalid", "--formats", "google", "--currency", "usd",
         "--map", "id=Item Code", "--map", "title=Label", "--map", "description=Long text",
         "--map", "price=Regular price EUR", "--map", "image_link=Picture", "--map", "link=Page"], capsys)
    root = ET.parse(out / "google-feed.en-CA.xml").getroot()
    assert root.findtext("channel/link") == "https://shop.example.ca/"
    assert root.find("channel/item").findtext(G + "price") == "15.00 USD"


def test_unused_columns_are_reported_on_stderr(fixtures, capsys):
    _, _, err = run([fixtures / "custom_headers.csv"], capsys)
    assert "columns not used: Item Code" in err


def test_module_invocation_exit_codes(fixtures, tool_dir):
    env = dict(os.environ, PYTHONUTF8="1")
    good = subprocess.run([sys.executable, "-m", "product_feed_gen", str(fixtures / "valid_products.csv"), "--strict"],
                          cwd=tool_dir, capture_output=True, text=True, env=env)
    bad = subprocess.run([sys.executable, "-m", "product_feed_gen", str(fixtures / "invalid_products.csv"), "--strict"],
                         cwd=tool_dir, capture_output=True, text=True, env=env)
    assert (good.returncode, bad.returncode) == (0, 1)
    assert "gtin-invalid" in bad.stdout
