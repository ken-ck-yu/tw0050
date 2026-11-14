import pytest

from twdata.universe.classify import is_common_stock, normalise_name


@pytest.mark.parametrize(
    ("code", "name", "expected"),
    [
        ("2330", "台積電", True),
        ("1101", "台泥", True),
        ("9958", "世紀鋼", True),
        ("2724", "富驛-KY", True),
        ("2501", "國建*", True),
        ("0050", "元大台灣50", False),  # ETF
        ("00878", "國泰永續高股息", False),
        ("2891B", "中信金乙特", False),  # preferred share
        ("123456", "某權證", False),  # six-digit warrant
        ("910708", "康師傅-DR", False),
        ("9103", "美德醫療-DR", False),
        ("9103", " 美德醫療-DR* ", False),
        ("0999", "x", False),
        ("233", "x", False),
        ("23300", "x", False),
        ("", "x", False),
        ("2330 ", "台積電", False),  # codes are matched exactly; callers pass stripped codes
    ],
)
def test_is_common_stock(code, name, expected):
    assert is_common_stock(code, name) is expected


def test_normalise_name_is_clean_name():
    assert normalise_name("\t國巨*") == "國巨"
    assert normalise_name("　台泥　") == "台泥"
    assert normalise_name("A**") == "A*"
