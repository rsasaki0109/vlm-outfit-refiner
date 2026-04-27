from __future__ import annotations

import pytest

from vlm import parse_json_object


def test_parse_json_object_plain() -> None:
    assert parse_json_object('{"a":1}') == {"a": 1}


def test_parse_json_object_fenced() -> None:
    s = "```json\n{\"a\": 1, \"b\": \"x\"}\n```"
    assert parse_json_object(s) == {"a": 1, "b": "x"}


def test_parse_json_object_with_extra_text_after() -> None:
    s = "{\"a\": 1}\n\n余計な説明"
    assert parse_json_object(s) == {"a": 1}


def test_parse_json_object_rejects_non_json() -> None:
    with pytest.raises(Exception):
        parse_json_object("not json")

