import json

from better_code_review_graph.tools import _estimate_payload_bytes


def test_estimate_payload_bytes_empty():
    # No arguments
    assert _estimate_payload_bytes() == 0
    # Empty list and empty dict as separate arguments
    assert _estimate_payload_bytes([], {}) == len(repr([])) + len(repr({}))


def test_estimate_payload_bytes_single_dict():
    payload = {"key": "value"}
    estimated = _estimate_payload_bytes(payload)
    actual_json_len = len(json.dumps(payload))
    # repr({"key": "value"}) is "{'key': 'value'}" (16 chars)
    # json.dumps({"key": "value"}) is '{"key": "value"}' (16 chars)
    # It might vary depending on quotes but repr is generally a good upper bound or equal
    assert estimated >= actual_json_len
    assert estimated == len(repr(payload))


def test_estimate_payload_bytes_multiple_payloads():
    p1 = {"a": 1}
    p2 = [{"b": 2}, {"c": 3}]
    estimated = _estimate_payload_bytes(p1, p2)
    expected = len(repr(p1)) + len(repr(p2))
    assert estimated == expected

    actual_json_len = len(json.dumps(p1)) + len(json.dumps(p2))
    assert estimated >= actual_json_len


def test_estimate_payload_bytes_with_strings_and_numbers():
    payload = {"name": "Jules", "age": 30, "skills": ["python", "testing"]}
    estimated = _estimate_payload_bytes(payload)
    actual_json_len = len(json.dumps(payload))
    assert estimated >= actual_json_len


def test_estimate_payload_bytes_nested():
    payload = {"outer": {"inner": [1, 2, 3]}}
    estimated = _estimate_payload_bytes(payload)
    actual_json_len = len(json.dumps(payload))
    assert estimated >= actual_json_len


def test_estimate_payload_bytes_overestimation_case():
    # JSON uses " ", repr uses ' ' for strings usually.
    # Boolean in JSON is true/false, in repr it's True/False.
    payload = {"bool": True, "none": None}
    estimated = _estimate_payload_bytes(payload)
    # repr: {'bool': True, 'none': None} -> 26 chars
    # json: {"bool": true, "none": null} -> 26 chars
    # Actually repr is often longer because of single vs double quotes and capitalized booleans/None
    actual_json_len = len(json.dumps(payload))
    assert estimated >= actual_json_len
