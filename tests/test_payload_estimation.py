import json

from better_code_review_graph.tools import _estimate_payload_bytes


def test_estimate_payload_bytes_empty():
    assert _estimate_payload_bytes() == 0


def test_estimate_payload_bytes_single_dict():
    d = {"key": "value", "int": 123, "bool": True, "none": None}
    estimate = _estimate_payload_bytes(d)
    actual_json_len = len(json.dumps(d))
    # repr uses ' while json uses "
    # repr uses True while json uses true
    # repr uses None while json uses null
    assert estimate >= actual_json_len
    assert isinstance(estimate, int)


def test_estimate_payload_bytes_list_of_dicts():
    payload = [{"a": 1}, {"b": 2}]
    estimate = _estimate_payload_bytes(payload)
    actual_json_len = len(json.dumps(payload))
    assert estimate >= actual_json_len


def test_estimate_payload_bytes_multiple_args():
    d1 = {"a": 1}
    d2 = {"b": 2}
    l1 = [{"c": 3}]
    # sum(len(repr(d1)), len(repr(d2)), len(repr(l1)))
    expected = len(repr(d1)) + len(repr(d2)) + len(repr(l1))
    assert _estimate_payload_bytes(d1, d2, l1) == expected


def test_estimate_payload_bytes_overestimation():
    # Example where repr is definitely longer than JSON
    d = {"key": "it's a string with single quote"}
    # repr(d) -> "{'key': \"it's a string with single quote\"}"
    # json.dumps(d) -> '{"key": "it\'s a string with single quote"}'
    estimate = _estimate_payload_bytes(d)
    actual_json_len = len(json.dumps(d))
    assert estimate >= actual_json_len
