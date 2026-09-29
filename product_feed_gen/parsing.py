"""Small parsers for the values found in product spreadsheets.

Every parser raises ValueError with a message meant for the shop owner, or
returns None when the value is not one of the known spellings.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from decimal import Decimal
from urllib.parse import urlsplit

# Active ISO 4217 alphabetic codes (checked against the standard's list).
CURRENCIES = frozenset(
    """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB
    BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD
    EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS
    INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD
    LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK
    NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK
    SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH
    UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWL""".split()
)


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def compact(text: str) -> str:
    """Lowercase, no accents, letters and digits only: 'Sold-Out' -> 'soldout'."""
    return re.sub(r"[^a-z0-9]", "", strip_accents(text).lower())


# ---------------------------------------------------------------- prices

# Currency written as a symbol: "$ CAD", "CA$", "US$", "EUR sign", "GBP sign".
_SYMBOLS = [
    (re.compile(r"(?i)\$\s*(?:CAD|CA)\b|\b(?:CAD|CA|C)\s*\$"), " CAD "),
    (re.compile(r"(?i)\$\s*(?:USD|US)\b|\b(?:USD|US)\s*\$"), " USD "),
    (re.compile("\u20ac"), " EUR "),
    (re.compile("\u00a3"), " GBP "),
]
_PRICE = re.compile(r"(?:([A-Za-z]{3})\s*)?(\d(?:[\d\s.,']*\d)?)\s*(?:([A-Za-z]{3}))?")
_SPACE_THOUSANDS = re.compile(r"\d{1,3}(?:[ ']\d{3})+(?:[.,]\d+)?")
_PRICE_HELP = "expected a number with an optional currency, e.g. 19.99, 19.99 CAD, $19.99 or 19,99"


def _plain_number(t: str) -> str:
    """Turn '1 299,99', '1,299.99' or '19,99' into '1299.99' / '19.99'."""
    t = re.sub(r"\s+", " ", t)
    if " " in t or "'" in t:
        if not _SPACE_THOUSANDS.fullmatch(t):
            raise ValueError(f"unexpected space in the number; {_PRICE_HELP}")
        t = t.replace(" ", "").replace("'", "")
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        thou = "." if dec == "," else ","
        head, _, tail = t.rpartition(dec)
        if not re.fullmatch(r"\d{1,3}(?:%s\d{3})+" % re.escape(thou), head):
            raise ValueError(f"mixed thousands and decimal separators; {_PRICE_HELP}")
        return head.replace(thou, "") + "." + tail
    if "," in t:
        parts = t.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            return ".".join(parts)
        if all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3:
            if len(parts) == 2:
                raise ValueError(
                    f"'{t}' is ambiguous (1.299 or 1299?); write it as {parts[0]}{parts[1]}.00 or {parts[0]}.{parts[1]}"
                )
            return "".join(parts)
        raise ValueError(f"unexpected comma in the number; {_PRICE_HELP}")
    if t.count(".") > 1:
        raise ValueError(f"more than one decimal point; {_PRICE_HELP}")
    return t


def parse_price(text: str) -> tuple[Decimal, str | None]:
    """Parse '19.99 CAD', 'CAD 19.99', '$19.99', '19,99' or '1 299,99 $'.

    Returns (amount, currency). The currency is None when the text has none
    or only a bare '$' (the caller decides which currency that means).
    """
    s = text.replace("\u00a0", " ").replace("\u202f", " ").strip()
    for pattern, code in _SYMBOLS:
        s = pattern.sub(code, s)
    s = s.replace("$", " ").strip()
    m = _PRICE.fullmatch(s)
    if not m:
        raise ValueError(f"'{text}' is not a price; {_PRICE_HELP}")
    before, number, after = m.groups()
    if before and after and before.upper() != after.upper():
        raise ValueError(f"'{text}' has two different currencies")
    code = (before or after or "").upper() or None
    if code and code not in CURRENCIES:
        raise ValueError(f"'{code}' is not an ISO 4217 currency code")
    amount = Decimal(_plain_number(number))
    if amount.as_tuple().exponent < -2:
        raise ValueError(f"'{text}' has more than two decimals")
    if amount <= 0:
        raise ValueError(f"'{text}' must be greater than zero")
    return amount.quantize(Decimal("0.01")), code


def money(amount: Decimal, currency: str) -> str:
    return f"{amount:.2f} {currency}"


# ---------------------------------------------------------------- GTIN

def gtin_check_digit(body: str) -> int:
    """Check digit for the digits that precede it (GS1 mod-10, weights 3,1,3,...)."""
    total = sum(int(ch) * (3 if i % 2 == 0 else 1) for i, ch in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def check_gtin(raw: str) -> tuple[str, str | None]:
    """Return (digits, problem). problem is None when GTIN-8/12/13/14 is valid."""
    digits = re.sub(r"[\s-]", "", raw)
    if not re.fullmatch(r"[0-9]+", digits):
        return digits, "GTIN must contain digits only"
    if len(digits) not in (8, 12, 13, 14):
        return digits, f"GTIN must have 8, 12, 13 or 14 digits, this one has {len(digits)}"
    expected = gtin_check_digit(digits[:-1])
    if int(digits[-1]) != expected:
        return digits, f"check digit is {digits[-1]}, expected {expected} for GTIN-{len(digits)}"
    return digits, None


# ---------------------------------------------------------------- enumerations

def _table(**groups: str) -> dict[str, str]:
    return {compact(word): name for name, words in groups.items() for word in words.split(",")}


_AVAILABILITY = _table(
    in_stock="in_stock,instock,available,en stock,disponible,in inventory,yes,y,true,1",
    out_of_stock=(
        "out_of_stock,outofstock,sold out,unavailable,indisponible,rupture de stock,"
        "en rupture,epuise,discontinued,no,n,false,0"
    ),
    preorder="preorder,pre-order,pre order,precommande,pre-commande",
    backorder="backorder,back order,back-order,available for order,sur commande",
)
_CONDITION = _table(
    new="new,brand new,neuf,neuve,nouveau",
    used="used,pre-owned,preowned,second hand,secondhand,occasion,d'occasion,usage",
    refurbished="refurbished,refurb,renewed,reconditionne,reconditionnee,remis a neuf",
)
_YES_NO = _table(**{"yes": "yes,y,true,1,oui", "no": "no,n,false,0,non"})
_RETURN_FEES = _table(
    free="free,free return,free returns,gratuit,retour gratuit,none,no fee",
    customer_pays="customer,customer pays,paid,shipping fee,return shipping fee,payant,client",
    restocking="restocking,restocking fee,frais de reapprovisionnement",
)


def parse_availability(text: str) -> str | None:
    return _AVAILABILITY.get(compact(text))


def parse_condition(text: str) -> str | None:
    return _CONDITION.get(compact(text))


def parse_yes_no(text: str) -> bool | None:
    value = _YES_NO.get(compact(text))
    return None if value is None else value == "yes"


def parse_return_fees(text: str) -> str | None:
    return _RETURN_FEES.get(compact(text))


# ---------------------------------------------------------------- dates

def _format_offset(offset: dt.timedelta) -> str:
    minutes = int(offset.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    hours, mins = divmod(abs(minutes), 60)
    return f"{sign}{hours:02d}:{mins:02d}"


def parse_when(text: str, tz_offset: str, end: bool = False) -> tuple[str, dt.date]:
    """Parse a date or datetime into Google's 'YYYY-MM-DDThh:mm+hh:mm' plus its date.

    A date without a time becomes 00:00 (start) or 23:59 (end) in tz_offset.
    """
    s = text.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            day = dt.date.fromisoformat(s)
            return f"{day.isoformat()}T{'23:59' if end else '00:00'}{tz_offset}", day
        moment = dt.datetime.fromisoformat(re.sub(r"(?i)z$", "+00:00", s.replace(" ", "T")))
    except ValueError:
        raise ValueError(f"'{text}' is not an ISO date (use YYYY-MM-DD or YYYY-MM-DDThh:mm)") from None
    offset = _format_offset(moment.utcoffset()) if moment.tzinfo else tz_offset
    return f"{moment:%Y-%m-%dT%H:%M}{offset}", moment.date()


def parse_date(text: str) -> dt.date:
    return parse_when(text, "+00:00")[1]


# ---------------------------------------------------------------- urls

def check_url(url: str, allow_http: bool) -> tuple[str, str] | None:
    """Return (severity, message) for the first problem with a URL, else None."""
    if re.search(r"\s", url):
        return "error", "contains spaces; encode them as %20"
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return "error", "must be a full URL starting with https://"
    if len(url) > 2000:
        return "error", "is longer than 2000 characters"
    if parts.scheme == "http":
        return ("warning" if allow_http else "error"), "uses http://; https:// is required"
    return None


# ---------------------------------------------------------------- weight, shipping, returns

_WEIGHT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|lb|lbs|oz)?", re.IGNORECASE)


def parse_weight(text: str) -> tuple[Decimal, str, bool]:
    """Return (value, unit, unit_was_assumed). Unit defaults to kg."""
    m = _WEIGHT.fullmatch(text.strip())
    if not m:
        raise ValueError(f"'{text}' is not a weight; use a number and a unit: 0.5 kg, 500 g, 2 lb, 8 oz")
    value = Decimal(m.group(1).replace(",", "."))
    if value <= 0:
        raise ValueError(f"'{text}' must be greater than zero")
    unit = (m.group(2) or "kg").lower()
    return value, "lb" if unit == "lbs" else unit, m.group(2) is None


def split_list(text: str) -> list[str]:
    """Split image lists written with | , or new lines (commas only before a URL)."""
    parts = re.split(r"[|\n]+|,(?=\s*https?://)", text)
    return [p.strip() for p in parts if p.strip()]


def parse_return_days(text: str) -> int:
    m = re.fullmatch(r"(\d+)\s*(?:days?|jours?|j)?", text.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"'{text}' is not a number of days (e.g. 30)")
    return int(m.group(1))
