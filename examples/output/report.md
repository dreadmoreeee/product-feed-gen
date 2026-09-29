# Product feed report: woodshop_products.csv

| Language | Products | OK | Warnings only | Errors |
|---|---|---|---|---|
| en-CA | 16 | 10 | 2 | 4 |
| fr-CA | 16 | 10 | 2 | 4 |

## en-CA: products with problems

| Row | ID | Severity | Field | Problem |
|---|---|---|---|---|
| 10 | WS-1009 | warning | shipping_weight | no unit in '2.5'; assuming kg |
| 12 | WS-1011 | warning | google_product_category | no google_product_category or product_type; recommended for matching and reporting |
| 14 | WS-1013 | error | gtin | gtin '2001000000015': check digit is 5, expected 2 for GTIN-13 |
| 15 | WS-1014 | error | image_link | image_link 'http://shop.example.ca/img/ws-1014.jpg' uses http://; https:// is required |
| 16 | WS-1015 | error | price | price is required |
| 17 | WS-1016 | error | title | title has 155 characters; the limit is 150 |

## fr-CA: products with problems

| Row | ID | Severity | Field | Problem |
|---|---|---|---|---|
| 5 | WS-1004 | error | description | description is required |
| 10 | WS-1009 | warning | shipping_weight | no unit in '2.5'; assuming kg |
| 12 | WS-1011 | warning | google_product_category | no google_product_category or product_type; recommended for matching and reporting |
| 14 | WS-1013 | error | gtin | gtin '2001000000015': check digit is 5, expected 2 for GTIN-13 |
| 15 | WS-1014 | error | image_link | image_link 'http://shop.example.ca/img/ws-1014.jpg' uses http://; https:// is required |
| 16 | WS-1015 | error | price | price is required |

Products with errors are left out of the feeds.
