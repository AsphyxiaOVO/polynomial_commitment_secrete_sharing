import json

import pytest

from gui.parsing import (bundle_from_json, bundle_to_json, parse_int, parse_int_list,
                         parse_optional_int, parse_point_sets)
from pcss.config import FIELD_MODULUS
from pcss.errors import ValidationError
from pcss.sharing import recover_message, split_secret


def test_parse_int():
    assert parse_int(" 42 ", "k") == 42
    assert parse_int(str(FIELD_MODULUS - 1), "x") == FIELD_MODULUS - 1
    for bad in ("", "  ", "1.5", "abc", "0x10"):
        with pytest.raises(ValidationError):
            parse_int(bad, "k")
    assert parse_optional_int("  ", "y") is None


def test_parse_int_list_and_point_sets():
    assert parse_int_list("1, 2,3  4", "T") == [1, 2, 3, 4]
    with pytest.raises(ValidationError):
        parse_int_list(" , ", "T")
    assert parse_point_sets("0,3\n\n0, 3, 8\n") == [[0, 3], [0, 3, 8]]
    with pytest.raises(ValidationError):
        parse_point_sets("\n \n")


def test_bundle_round_trip():
    result = split_secret("导出 / インポート 🔁", 2, 3)
    meta, shares = bundle_from_json(bundle_to_json(result.metadata, result.shares))
    assert meta == result.metadata and shares == list(result.shares)
    assert recover_message(shares[1:], meta) == "导出 / インポート 🔁"


@pytest.mark.parametrize("text", [
    "not json",
    "[]",
    json.dumps({"metadata": {}}),
    json.dumps({"metadata": {"threshold": 2}, "shares": []}),
    json.dumps({"metadata": {"threshold": 2, "share_count": 3, "original_length": 1,
                             "chunk_count": 1}, "shares": [{"x": 1}]}),
    json.dumps({"metadata": {"threshold": 2, "share_count": 3, "original_length": 1,
                             "chunk_count": 1}, "shares": "oops"}),
])
def test_bundle_from_json_rejects_malformed(text):
    with pytest.raises(ValidationError):
        bundle_from_json(text)
