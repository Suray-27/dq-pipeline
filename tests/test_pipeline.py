import sys
import os
import json
import pandas as pd
import pytest
sys.path.insert(0, "include/src")


# ─── Test Extract ──────────────────────────────────────────────
def test_extract_loads_csv():
    from extract import extract
    df = extract("include/data/raw/customers.csv")
    assert len(df) == 9
    assert "id" in df.columns
    assert "email" in df.columns


def test_extract_correct_columns():
    from extract import extract
    df = extract("include/data/raw/customers.csv")
    expected_cols = ["id", "name", "email", "signup_dt", "status", "age"]
    assert list(df.columns) == expected_cols


# ─── Test Transform ────────────────────────────────────────────
def test_transform_lowercase_status():
    from transform import transform
    df = pd.DataFrame({
        "id": [1, 2],
        "name": ["Alice", "Bob"],
        "email": ["a@b.com", "c@d.com"],
        "signup_dt": ["2024-01-01", "2024-02-01"],
        "status": ["ACTIVE", "Pending"],
        "age": [25.0, 30.0],
    })
    result = transform(df)
    assert result["status"].tolist() == ["active", "pending"]


def test_transform_trims_whitespace():
    from transform import transform
    df = pd.DataFrame({
        "id": [1],
        "name": ["  Alice  "],
        "email": ["a@b.com"],
        "signup_dt": ["2024-01-01"],
        "status": ["active"],
        "age": [25.0],
    })
    result = transform(df)
    assert result["name"][0] == "Alice"


def test_transform_preserves_row_count():
    from extract import extract
    from transform import transform
    df = extract("include/data/raw/customers.csv")
    result = transform(df)
    assert len(result) == len(df)


# ─── Test Validate ─────────────────────────────────────────────
def test_validate_catches_null():
    from validate import validate
    df = pd.DataFrame({
        "age": [25.0, None, 30.0]
    })
    rules = [{"column": "age", "rule_type": "not_null", "params": {}, "reasoning": ""}]
    passed, failed, violations = validate(df, rules)
    assert len(failed) == 1
    assert violations[0]["rule_type"] == "not_null"


def test_validate_catches_duplicate():
    from validate import validate
    df = pd.DataFrame({
        "id": [1, 2, 1]
    })
    rules = [{"column": "id", "rule_type": "unique", "params": {}, "reasoning": ""}]
    passed, failed, violations = validate(df, rules)
    assert len(failed) == 2
    assert violations[0]["rule_type"] == "unique"


def test_validate_catches_out_of_range():
    from validate import validate
    df = pd.DataFrame({
        "age": [25.0, 150.0, 30.0]
    })
    rules = [{
        "column": "age",
        "rule_type": "in_range",
        "params": {"min": 0, "max": 120},
        "reasoning": ""
    }]
    passed, failed, violations = validate(df, rules)
    assert len(failed) == 1
    assert violations[0]["value"] == "150.0"


def test_validate_catches_invalid_email():
    from validate import validate
    df = pd.DataFrame({
        "email": ["valid@example.com", "invalid-email", "another@test.com"]
    })
    rules = [{
        "column": "email",
        "rule_type": "regex",
        "params": {"pattern": r"^[\w.+-]+@[\w-]+\.[\w.-]+$"},
        "reasoning": ""
    }]
    passed, failed, violations = validate(df, rules)
    assert len(failed) == 1


def test_validate_catches_allowed_values():
    from validate import validate
    df = pd.DataFrame({
        "status": ["active", "INVALID", "pending"]
    })
    rules = [{
        "column": "status",
        "rule_type": "allowed_values",
        "params": {"values": ["active", "inactive", "pending"]},
        "reasoning": ""
    }]
    passed, failed, violations = validate(df, rules)
    assert len(failed) == 1


def test_validate_passes_clean_data():
    from validate import validate
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "age": [25.0, 30.0, 35.0]
    })
    rules = [
        {"column": "id", "rule_type": "unique", "params": {}, "reasoning": ""},
        {"column": "age", "rule_type": "not_null", "params": {}, "reasoning": ""},
    ]
    passed, failed, violations = validate(df, rules)
    assert len(passed) == 3
    assert len(failed) == 0
    assert len(violations) == 0


# ─── Test Schema Hash ──────────────────────────────────────────
def test_schema_hash_same_schema():
    from ai_rules import get_schema_hash
    df1 = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    df2 = pd.DataFrame({"id": [3, 4], "name": ["Carol", "Dave"]})
    assert get_schema_hash(df1) == get_schema_hash(df2)


def test_schema_hash_different_schema():
    from ai_rules import get_schema_hash
    df1 = pd.DataFrame({"id": [1], "name": ["Alice"]})
    df2 = pd.DataFrame({"id": [1], "name": ["Alice"], "phone": ["123"]})
    assert get_schema_hash(df1) != get_schema_hash(df2)


# ─── Test File Hash ────────────────────────────────────────────
def test_file_hash_same_file():
    from pipeline import get_file_hash
    h1 = get_file_hash("include/data/raw/customers.csv")
    h2 = get_file_hash("include/data/raw/customers.csv")
    assert h1 == h2


def test_file_hash_different_files():
    from pipeline import get_file_hash
    h1 = get_file_hash("include/data/raw/customers.csv")
    h2 = get_file_hash("include/data/raw/transactions.csv")
    assert h1 != h2