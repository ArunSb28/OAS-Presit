from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.generator import generate_tests, gen_value, build_request


def test_example_generation_from_body_examples():
    op = {
        "id": "test_create",
        "method": "POST",
        "path": "/items",
        "full_path": "/items",
        "parameters": [
            {"name": "X-Client", "in": "header", "required": True, "example": "client-123", "schema": {"type": "string"}}
        ],
        "request_body": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name", "price"],
                        "properties": {
                            "name": {"type": "string"},
                            "price": {"type": "number"},
                            "category": {"type": "string"},
                        },
                    },
                    "examples": {
                        "laptop": {
                            "summary": "Laptop item",
                            "value": {"name": "MacBook Pro", "price": 1999.99, "category": "electronics"},
                        },
                        "coffee": {
                            "summary": "Coffee beans",
                            "value": {"name": "Espresso Beans", "price": 14.50, "category": "groceries"},
                        },
                    },
                }
            },
        },
    }

    tests = generate_tests(op, [])
    # Verify dedicated test cases from examples
    ex_tests = [t for t in tests if t["name"].startswith("Example:")]
    assert len(ex_tests) == 2
    assert ex_tests[0]["name"] == "Example: Laptop item"
    assert ex_tests[0]["request"]["body"] == {"name": "MacBook Pro", "price": 1999.99, "category": "electronics"}
    assert ex_tests[0]["request"]["headers"]["X-Client"] == "client-123"

    assert ex_tests[1]["name"] == "Example: Coffee beans"
    assert ex_tests[1]["request"]["body"] == {"name": "Espresso Beans", "price": 14.50, "category": "groceries"}


def test_auto_generation_when_examples_not_present():
    op = {
        "id": "test_auto",
        "method": "POST",
        "path": "/users",
        "full_path": "/users",
        "parameters": [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^usr_[0-9]{4}$"}}
        ],
        "request_body": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["email", "age"],
                        "properties": {
                            "email": {"type": "string", "format": "email"},
                            "age": {"type": "integer", "minimum": 18, "maximum": 120},
                        },
                    }
                }
            },
        },
    }

    tests = generate_tests(op, [])
    # No example test cases
    ex_tests = [t for t in tests if t["name"].startswith("Example:")]
    assert len(ex_tests) == 0

    # Minimal and maximal are auto-generated
    min_test = next(t for t in tests if "Minimal" in t["name"])
    assert min_test["request"]["path_params"]["id"].startswith("usr_")
    assert min_test["request"]["body"]["email"] == "user@example.com"
    assert 18 <= min_test["request"]["body"]["age"] <= 120


def test_property_level_examples():
    schema = {
        "type": "object",
        "required": ["code", "desc"],
        "properties": {
            "code": {"type": "string", "example": "DISCOUNT50"},
            "desc": {"type": "string"},  # no example -> auto-generated
        },
    }
    val = gen_value(schema, "min")
    assert val["code"] == "DISCOUNT50"
    assert isinstance(val["desc"], str) and len(val["desc"]) > 0
