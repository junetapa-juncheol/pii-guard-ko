import datetime as dt

from bench import Gen
from pii_guard_ko import checks


def test_resident_checksums():
    g = Gen(1)
    for _ in range(50):
        assert checks.rrn_ok(g.resident().replace("-", ""))
        assert checks.frn_ok(g.resident(foreign=True).replace("-", ""))
        assert not checks.rrn_ok(g.resident(valid=False).replace("-", ""))


def test_birth_date():
    assert checks.birth_date("0002291000000") is None
    assert checks.birth_date("0002293000000") == dt.date(2000, 2, 29)
    assert checks.birth_date("9913011000000") is None
    assert checks.birth_date("9902301000000") is None
    assert checks.birth_date("8501019000000") is None
    assert checks.birth_date("8501011000000") == dt.date(1985, 1, 1)
    assert checks.birth_date("2501013000000", today=dt.date(2024, 1, 1)) is None


def test_luhn_and_brand():
    g = Gen(2)
    for _ in range(50):
        card = g.card("4")
        assert checks.luhn_ok(card)
        assert checks.card_brand(card) == "visa"
    assert checks.card_brand("2026102112345678") is None
    assert checks.card_brand(g.card("37", 15)) == "amex"


def test_brn():
    g = Gen(3)
    for _ in range(50):
        assert checks.brn_ok(g.brn().replace("-", ""))


def test_fake_phone():
    assert checks.fake_phone("1234", "5678")
    assert checks.fake_phone("0000", "0000")
    assert checks.fake_phone("1111", "2222")
    assert checks.fake_phone("5678", "5678")
    assert not checks.fake_phone("2918", "4471")
