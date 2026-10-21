"""Checksums and format rules for Korean identifiers."""
import datetime as dt

RRN_WEIGHTS = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)
CENTURY = {"1": 1900, "2": 1900, "3": 2000, "4": 2000,
           "5": 1900, "6": 1900, "7": 2000, "8": 2000}
RUN_UP = "0123456789" * 3
RUN_DOWN = RUN_UP[::-1]


def birth_date(d, today=None):
    """Birth date encoded in a 13-digit RRN/FRN, or None if impossible."""
    base = CENTURY.get(d[6])
    if base is None:
        return None
    try:
        born = dt.date(base + int(d[:2]), int(d[2:4]), int(d[4:6]))
    except ValueError:
        return None
    if born > (today or dt.date.today()):
        return None
    return born


def _weighted(d):
    return sum(int(d[i]) * w for i, w in enumerate(RRN_WEIGHTS))


def rrn_ok(d):
    return (11 - _weighted(d) % 11) % 10 == int(d[12])


def frn_ok(d):
    return (13 - _weighted(d) % 11) % 10 == int(d[12])


def luhn_ok(d):
    total = 0
    for i, ch in enumerate(reversed(d)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def brn_ok(d):
    keys = (1, 3, 7, 1, 3, 7, 1, 3, 5)
    total = sum(int(d[i]) * keys[i] for i in range(8))
    last = int(d[8]) * 5
    total += last + last // 10
    return (10 - total % 10) % 10 == int(d[9])


def card_brand(d):
    n = len(d)
    two, three, four = int(d[:2]), int(d[:3]), int(d[:4])
    if d[0] == "4" and n in (13, 16, 19):
        return "visa"
    if n == 16 and (51 <= two <= 55 or 2221 <= four <= 2720):
        return "mastercard"
    if n == 15 and two in (34, 37):
        return "amex"
    if 16 <= n <= 19 and 3528 <= four <= 3589:
        return "jcb"
    if n == 16 and (four == 6011 or two == 65 or 644 <= three <= 649):
        return "discover"
    if 16 <= n <= 19 and two == 62:
        return "unionpay"
    if n == 14 and (two in (36, 38, 39) or 300 <= three <= 305):
        return "diners"
    if n == 16 and d[0] == "9":
        return "domestic"
    return None


TEST_CARDS = {
    "4111111111111111", "4242424242424242", "4000056655665556", "4012888888881881",
    "5555555555554444", "5105105105105100", "5200828282828210", "378282246310005",
    "371449635398431", "6011111111111117", "3530111333300000", "3566002020360505",
}


def fake_digits(d):
    """All one digit, or a straight run such as 12345678."""
    return len(set(d)) == 1 or d in RUN_UP or d in RUN_DOWN


def fake_phone(mid, last):
    if "0000" in (mid, last) or mid == last:
        return True
    if fake_digits(mid + last):
        return True
    return fake_digits(mid) and fake_digits(last)
