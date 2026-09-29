"""Data model shared by the reader, the validator and the writers."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

ERROR = "error"
WARNING = "warning"

LANG_TAGS = {"en": "en-CA", "fr": "fr-CA"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    field: str
    message: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "field": self.field,
            "message": self.message,
        }


@dataclass
class Options:
    """Settings that change how rows are interpreted."""

    default_currency: str = "CAD"
    allow_http: bool = False  # downgrade http:// links from error to warning
    today: dt.date = field(default_factory=dt.date.today)
    tz_offset: str = "-05:00"  # used for date-only sale windows
    country: str = "CA"  # applicable country of the return policy


@dataclass
class Shipping:
    country: str
    price: Decimal
    currency: str


@dataclass
class Product:
    """One product as seen in one language, already normalised."""

    row: int
    lang: str  # "en" or "fr"
    id: str = ""
    title: str = ""
    description: str = ""
    link: str = ""
    image_link: str = ""
    additional_image_links: list[str] = field(default_factory=list)
    availability: str = ""  # in_stock / out_of_stock / preorder / backorder
    condition: str = "new"  # new / used / refurbished
    brand: str = ""
    gtin: str = ""
    mpn: str = ""
    identifier_exists: bool | None = None
    price: Decimal | None = None
    sale_price: Decimal | None = None
    currency: str = ""
    sale_start: str = ""  # ISO 8601 with offset, as Google wants it
    sale_end: str = ""
    sale_start_date: dt.date | None = None
    sale_end_date: dt.date | None = None
    price_valid_until: dt.date | None = None
    google_product_category: str = ""
    product_type: str = ""
    weight_value: Decimal | None = None
    weight_unit: str = ""
    shipping: list[Shipping] = field(default_factory=list)
    return_days: int | None = None
    return_fees: str = ""  # free / customer_pays / restocking
    return_country: str = "CA"
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity: str, code: str, field_name: str, message: str) -> None:
        self.issues.append(Issue(severity, code, field_name, message))

    @property
    def tag(self) -> str:
        return LANG_TAGS.get(self.lang, self.lang)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.warnings:
            return "warning"
        return "ok"

    @property
    def category(self) -> str:
        return self.google_product_category or self.product_type

    @property
    def shipping_weight(self) -> str:
        if self.weight_value is None:
            return ""
        return f"{format(self.weight_value.normalize(), 'f')} {self.weight_unit}"

    def sale_is_active(self, today: dt.date) -> bool:
        """True when a sale price exists and today is inside its window (if any)."""
        if self.sale_price is None:
            return False
        if self.sale_start_date and today < self.sale_start_date:
            return False
        if self.sale_end_date and today > self.sale_end_date:
            return False
        return True
