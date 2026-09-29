# product-feed-gen

Turn a product spreadsheet (CSV) into a **Google Merchant Center feed**, a **Meta catalog CSV** and **schema.org Product JSON-LD**, after checking every product for the mistakes that get items disapproved. Built for small Canadian shops: CAD by default, prices without tax, English and French feeds from one file, no dependencies.

```
python -m product_feed_gen products.csv --out feeds --strict
```

```python
from product_feed_gen import read_table, process, render_google_feed

table = read_table("products.csv")
products = process(table)                      # one Product per row and language, each with .issues
good = [p for p in products if p.tag == "en-CA" and not p.errors]
xml = render_google_feed(good, "en-CA", shop_name="My shop", shop_url="https://shop.example.ca/")
```

- **One CSV, three outputs.** Google RSS 2.0 feed (`xmlns:g`, escaped by `xml.etree`, so `&` and `<` in titles are safe), Meta catalog CSV with Meta's column names and availability words, and JSON-LD as a JSON file plus ready-to-paste `<script type="application/ld+json">` blocks.
- **Errors and warnings per product.** Products with errors are left out of the feeds (`--include-invalid` keeps them). The report is text, Markdown or JSON, and `--strict` exits with status 1 when any product has an error, so it can run in CI (see `examples/ci/`).
- **Tolerant input.** Header names such as `SKU`, `Product Name`, `Prix`, `g:price` are recognised; anything else can be mapped with `--map price="Regular price"` or a JSON file. Comma, semicolon, tab or pipe separators; UTF-8 or Excel's Windows-1252. Prices like `19.99 CAD`, `$19.99`, `19,99`, `1 299,99 $`. Availability like `In stock`, `sold out`, `en stock`, `pre-order`.
- **Bilingual.** Add `title_fr`, `description_fr`, `link_fr` (and the `_en` ones) and you get two feeds, `en-CA` and `fr-CA`, with the language in the file names.
- **No dependencies.** Standard library only, Python 3.10+.

## Measured result

The demo shop is invented (`examples/woodshop_products.csv`: 16 products, English and French columns, `shop.example.ca`). Four rows are broken on purpose: a wrong GTIN check digit, an `http://` image, a missing price and a 155-character title. Run on 2026-09-29:

```
$ python -m product_feed_gen examples/woodshop_products.csv --out examples/output --today 2026-09-29 --shop-name "Cedar & Pine Woodshop" --shop-url https://shop.example.ca/ --shop-description "Handmade hardwood kitchenware and home goods" --strict
product-feed-gen report for woodshop_products.csv

[en-CA]
row 10  WS-1009  Maple Salad Bowl Set (2 pieces)  -- 0 errors, 1 warning
  WARNING  weight-unit-assumed      no unit in '2.5'; assuming kg
row 12  WS-1011  Cedar Planter Box  -- 0 errors, 1 warning
  WARNING  category-missing         no google_product_category or product_type; recommended for matching and reporting
row 14  WS-1013  Pine Bookends, Pair  -- 1 error, 0 warnings
  ERROR    gtin-invalid             gtin '2001000000015': check digit is 5, expected 2 for GTIN-13
row 15  WS-1014  Ash Cheese Board  -- 1 error, 0 warnings
  ERROR    image_link-url           image_link 'http://shop.example.ca/img/ws-1014.jpg' uses http://; https:// is required
row 16  WS-1015  Cherry Jewelry Box  -- 1 error, 0 warnings
  ERROR    price-missing            price is required
row 17  WS-1016  Handmade Solid Hardwood Kitchen Utensil Set w...  -- 1 error, 0 warnings
  ERROR    title-too-long           title has 155 characters; the limit is 150

[fr-CA]
row 5  WS-1004  Range-épices mural en chêne  -- 1 error, 0 warnings
  ERROR    description-missing      description is required
row 10  WS-1009  Ensemble de bols à salade en érable (2 pièces)  -- 0 errors, 1 warning
  WARNING  weight-unit-assumed      no unit in '2.5'; assuming kg
row 12  WS-1011  Bac à fleurs en cèdre  -- 0 errors, 1 warning
  WARNING  category-missing         no google_product_category or product_type; recommended for matching and reporting
row 14  WS-1013  Serre-livres en pin, paire  -- 1 error, 0 warnings
  ERROR    gtin-invalid             gtin '2001000000015': check digit is 5, expected 2 for GTIN-13
row 15  WS-1014  Planche à fromage en frêne  -- 1 error, 0 warnings
  ERROR    image_link-url           image_link 'http://shop.example.ca/img/ws-1014.jpg' uses http://; https:// is required
row 16  WS-1015  Boîte à bijoux en merisier  -- 1 error, 0 warnings
  ERROR    price-missing            price is required

en-CA: 16 products: 10 ok, 2 with warnings only, 4 with errors
fr-CA: 16 products: 10 ok, 2 with warnings only, 4 with errors
Products with errors are left out of the feeds.
wrote examples\output\google-feed.en-CA.xml
wrote examples\output\meta-catalog.en-CA.csv
wrote examples\output\jsonld.en-CA.json
wrote examples\output\jsonld.en-CA.html
wrote examples\output\google-feed.fr-CA.xml
wrote examples\output\meta-catalog.fr-CA.csv
wrote examples\output\jsonld.fr-CA.json
wrote examples\output\jsonld.fr-CA.html
wrote examples\output\report.txt
$ echo $?
1
```

Each feed has the 12 valid products. `examples/output/google-feed.en-CA.xml` starts like this:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">
  <channel>
    <title>Cedar &amp; Pine Woodshop</title>
    <link>https://shop.example.ca/</link>
    <description>Handmade hardwood kitchenware and home goods</description>
    <language>en-CA</language>
    <item>
      <g:id>WS-1001</g:id>
      <g:title>Maple Cutting Board, 40 cm</g:title>
      <g:description>Hand-finished rock maple board with a juice groove. Sealed with food-safe mineral oil &amp; beeswax.</g:description>
      <g:link>https://shop.example.ca/en/maple-cutting-board</g:link>
      <g:image_link>https://shop.example.ca/img/ws-1001.jpg</g:image_link>
      <g:additional_image_link>https://shop.example.ca/img/ws-1001-b.jpg</g:additional_image_link>
      <g:additional_image_link>https://shop.example.ca/img/ws-1001-c.jpg</g:additional_image_link>
      <g:availability>in_stock</g:availability>
      <g:price>48.00 CAD</g:price>
      <g:condition>new</g:condition>
      <g:brand>Cedar &amp; Pine Woodshop</g:brand>
      <g:gtin>2001000000012</g:gtin>
      <g:mpn>CP-CB-40</g:mpn>
      ...
```

One JSON-LD block from `examples/output/jsonld.en-CA.html` (a product on sale, with shipping and a return policy):

```html
<!-- WS-1002 -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Walnut Serving Tray",
  "description": "Black walnut tray with routed handles. Each piece is one solid board, so the grain is unique.",
  "sku": "WS-1002",
  "image": [
    "https://shop.example.ca/img/ws-1002.jpg",
    "https://shop.example.ca/img/ws-1002-b.jpg"
  ],
  "brand": {
    "@type": "Brand",
    "name": "Cedar & Pine Woodshop"
  },
  "category": "Kitchen > Serving",
  "weight": {
    "@type": "QuantitativeValue",
    "value": 2.2,
    "unitCode": "KGM"
  },
  "offers": {
    "@type": "Offer",
    "url": "https://shop.example.ca/en/walnut-serving-tray",
    "priceCurrency": "CAD",
    "price": "54.00",
    "priceSpecification": [
      {
        "@type": "UnitPriceSpecification",
        "priceType": "https://schema.org/ListPrice",
        "price": "64.00",
        "priceCurrency": "CAD"
      }
    ],
    "priceValidUntil": "2026-10-15",
    "availability": "https://schema.org/InStock",
    "itemCondition": "https://schema.org/NewCondition",
    "shippingDetails": {
      "@type": "OfferShippingDetails",
      "shippingRate": {
        "@type": "MonetaryAmount",
        "value": "12.00",
        "currency": "CAD"
      },
      "shippingDestination": {
        "@type": "DefinedRegion",
        "addressCountry": "CA"
      }
    },
    "hasMerchantReturnPolicy": {
      "@type": "MerchantReturnPolicy",
      "applicableCountry": "CA",
      "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
      "merchantReturnDays": 30,
      "returnFees": "https://schema.org/FreeReturn"
    }
  }
}
</script>
```

```
$ python -m pytest -q -p no:cacheprovider --import-mode=importlib product-feed-gen
...................................                                      [100%]
179 passed in 0.74s
```

The tests need no network: they parse the generated XML back, read the Meta CSV with `csv`, load the JSON-LD blocks with `json`, and run the CLI for exit codes.

## Input columns

Only the first block is needed for a feed that passes the checks; the rest is optional.

| Field | Notes |
|---|---|
| `id`, `title`, `description`, `link`, `image_link` | Required. `title_en`/`title_fr`, `description_en`/`description_fr`, `link_en`/`link_fr` for two languages. |
| `price`, `availability` | Required. `currency` optional (default `CAD`, `--currency` changes it). |
| `brand` + `gtin` or `mpn` | Required, unless `identifier_exists` is `no` (handmade or custom goods). |
| `condition` | `new` (the default when empty), `used`, `refurbished`. |
| `sale_price` | Must be lower than `price`. Dates: `sale_price_effective_date` as `2026-09-01/2026-10-15`, or `sale_start` and `sale_end`. |
| `additional_image_links` | Separated by `\|` or new lines, up to 10. |
| `shipping_weight` | `1.5 kg`, `500 g`, `2 lb`, `8 oz`. Without a unit, kg is assumed (warning). |
| `google_product_category`, `product_type` | Free text or Google's category ID; at least one is recommended. |
| `price_valid_until` | Date; goes to JSON-LD `priceValidUntil`. |
| `shipping` | `CA:9.99` or `CA:9.99 CAD`, several separated by `\|`. |
| `return_days`, `return_fees` | `30` and `free` / `customer pays` / `restocking fee`. Used for `MerchantReturnPolicy`; `0` days means returns are not permitted. |

## What is checked

Errors (the product stays out of the feeds): missing id, title, description, link, image, availability or price; missing brand, or missing gtin and mpn, unless `identifier_exists=no`; GTIN-8/12/13/14 check digit and length; price not a number with an ISO 4217 currency (`19.99 CAD`, `$19.99`, `19,99`); `sale_price` not lower than `price`; sale window that ends before it starts; link or image that is not `https://`; title over 150 characters; description over 5000; id over 50; availability or condition outside the known words; more than 10 additional images; malformed shipping, weight, return or date values; duplicate ids (every repeat after the first).

Warnings: no category or product type, weight without a unit, all-capitals title, a sale that has already ended, `price_valid_until` in the past, a translation column left empty (the base column is used), no brand for Meta, `identifier_exists=no` together with a gtin or mpn.

**This is not an official validator.** The checks cover common Merchant Center requirements as I understand them. Merchant Center applies more rules (category-specific attributes, policy review, landing-page checks) and changes them over time, so a clean report does not promise approval.

## Canadian specifics

- **Currency** defaults to `CAD`. A `$` with no code is read as the default currency; `US$` or `USD` is respected.
- **Prices are submitted without tax.** For Canada, Merchant Center expects the price excluding GST/HST/PST/QST, and this tool never adds tax or writes a `tax` attribute. Put the pre-tax price in `price`. This differs from the US setup, where sales tax is configured in Merchant Center's tax settings; check Google's current Canada requirements if your account is set up differently.
- **Bilingual shops.** With `_en` and `_fr` columns you get `google-feed.en-CA.xml` and `google-feed.fr-CA.xml` (and the same for `meta-catalog`, `jsonld`). `--lang en` or `--lang fr` builds one. The `price` column is shared, so `19,99` written by a French spreadsheet is read correctly in both feeds.
- Excel in French Canada often saves `;`-separated Windows-1252 files; both are detected.
- A date-only sale window is turned into `00:00` to `23:59` in the offset from `--tz-offset` (default `-05:00`). Give full times such as `2026-09-01T00:00-04:00` if the exact hour matters.

## CLI

```
product-feed-gen products.csv [--out DIR] [--formats google,meta,jsonld] [--lang auto|en|fr]
                 [--currency CAD] [--map FIELD=HEADER ...] [--mapping map.json]
                 [--report text|markdown|json] [--report-file FILE]
                 [--strict] [--include-invalid] [--allow-http] [--country CA]
                 [--tz-offset -05:00] [--today YYYY-MM-DD]
                 [--shop-name NAME] [--shop-url URL] [--shop-description TEXT]
```

Without `--out` only the report is printed. Exit status: `0` normally, `1` with `--strict` when a product has an error, `2` for unreadable files or bad options. Install with `pip install .` to get the `product-feed-gen` command, or run `python -m product_feed_gen` from this folder.

## Limitations

- **Links and images are not fetched.** Only their shape is checked; a dead URL or a wrong image size will not be caught.
- **`https` is required** for links and images. Google also accepts `http`; I made it an error because a shop in 2026 should not need it. `--allow-http` turns it into a warning.
- **The return policy goes to JSON-LD only.** Google does not read return policies from product feed rows (they are set in Merchant Center), and Meta catalogs have no such column.
- **Shipping is simplified** to `country:price` (Google: country and price; Meta: `CA:::12.00 CAD`). No regions, services, delivery times or free-shipping thresholds.
- **GTINs are checked for length and check digit only**, not looked up in the GS1 registry. Category text is not checked against Google's taxonomy.
- **Brand is required** (unless `identifier_exists=no`) as the specification of this tool says; Google itself is slightly more lenient for some categories.
- **Ambiguous prices are rejected:** `1,299` could be 1.299 or 1299, so write `1299.00`. More than two decimals is an error, not a rounding.
- Variants (`item_group_id`, size, colour), multipacks and product bundles are not supported yet.
- Row numbers in the report count CSV records with the header as row 1, which matches a spreadsheet unless a cell contains a line break.

## Author

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
