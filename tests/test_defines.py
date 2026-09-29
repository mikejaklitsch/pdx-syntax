from pdx_syntax.defines import parse_defines


def test_parse_defines_namespaces_values_comments(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text(
        "NMarket = {\n"
        "\tFOOD_PRICE = 0.05 # gold per food\n"
        "\tNESTED = { 1 2 }\n"
        "}\n"
        "NPop = {\n"
        "\tDEVELOPMENT_SCALE_ON_DEMAND = 0.05\n"
        "}\n", encoding="utf-8-sig")
    d = parse_defines(f)
    assert d["FOOD_PRICE"] == {"ns": "NMarket", "value": "0.05", "comment": "gold per food", "line": 2}
    assert d["DEVELOPMENT_SCALE_ON_DEMAND"]["ns"] == "NPop"
    assert "NESTED" not in d
