"""Arg coercion: structured args get parsed, free-text args never do."""
from coercion import coerce_args


def test_json_array_parsed():
    args = {"steps": '[{"action": "wait"}]'}
    coerce_args(args)
    assert args["steps"] == [{"action": "wait"}]


def test_csv_string_split():
    args = {"checks": "seo, performance"}
    coerce_args(args)
    assert args["checks"] == ["seo", "performance"]


def test_bare_string_wrapped():
    args = {"checks": "seo"}
    coerce_args(args)
    assert args["checks"] == ["seo"]


def test_bool_coerced():
    args = {"force": "true", "once": "False"}
    coerce_args(args)
    assert args["force"] is True
    assert args["once"] is False


def test_free_text_body_untouched():
    # intercept_network body is a JSON *string* by design — must never be parsed
    args = {"body": '{"error": "fail"}'}
    coerce_args(args)
    assert args["body"] == '{"error": "fail"}'


def test_free_text_value_untouched():
    args = {"value": "false", "expected": "[draft]"}
    coerce_args(args)
    assert args["value"] == "false"
    assert args["expected"] == "[draft]"


def test_invalid_json_left_as_string():
    args = {"steps": "[not json"}
    coerce_args(args)
    assert args["steps"] == "[not json"


def test_non_string_values_untouched():
    args = {"steps": [{"action": "wait"}], "force": True}
    coerce_args(args)
    assert args["steps"] == [{"action": "wait"}]
    assert args["force"] is True
