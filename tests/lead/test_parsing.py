import pytest

from twdata.common import parsing as P


def test_numbers():
    assert P.parse_number("1,234.50") == 1234.5
    assert P.parse_number("- 0.50") == -0.5
    assert P.parse_number("+ 3.50") == 3.5
    for empty in ("", "--", "-", "N/A", "X0.00", "X"):
        assert P.parse_number(empty) is None
    with pytest.raises(P.ParseError):
        P.parse_number("abc")


def test_ints():
    assert P.parse_int("31,646,861") == 31646861
    assert P.parse_int("12.0") == 12
    assert P.parse_int("--") is None
    with pytest.raises(P.ParseError):
        P.parse_int("12.5")


def test_clean_name():
    assert P.clean_name("\t國巨*") == "國巨"
    assert P.clean_name("　台積電 ") == "台積電"
    assert P.clean_name("矽力*-KY") == "矽力*-KY"


def test_sign_cells():
    assert P.parse_sign("<p style ='color:red'>+</p>") == 1
    assert P.parse_sign("<p style ='color:green'>-</p>") == -1
    assert P.parse_sign("<p> </p>") == 0
    assert P.parse_sign("<p>X</p>") is None
    with pytest.raises(P.ParseError):
        P.parse_sign("<p>?</p>")


def test_strip_tags():
    assert P.strip_tags("<b>a</b>b") == "ab"


def test_dash_runs_are_empty_markers():
    for cell in ("----", "---", "--"):
        assert P.parse_number(cell) is None


def test_tpex_change_cell():
    assert P.parse_tpex_change("+ 3.50") == (3.5, False)
    assert P.parse_tpex_change("- 0.50") == (-0.5, False)
    assert P.parse_tpex_change("---") == (None, False)
    for ex in ("除息", "除權", "除權息"):
        assert P.parse_tpex_change(ex) == (None, True)
    with pytest.raises(P.ParseError):
        P.parse_tpex_change("停牌")


def test_tpex_fixture_rows_parse():
    import json
    from pathlib import Path

    base = Path(__file__).resolve().parents[1] / "fixtures" / "lead" / "tpex"
    seen_ex = False
    for name in ("otc_20160601.json", "otc_20200601.json", "otc_20250602.json"):
        data = json.loads((base / name).read_text(encoding="utf-8"))["tables"][0]["data"]
        for row in data:
            for cell in row[2:7]:  # close, change, open, high, low
                if cell.strip() in ("除息", "除權"):
                    seen_ex = True
                    assert P.parse_tpex_change(cell)[1] is True
                else:
                    P.parse_tpex_change(cell)
    assert seen_ex
