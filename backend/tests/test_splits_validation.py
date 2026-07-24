from decimal import Decimal

import pytest

from app.errors import ValidationError
from app.services.splits import validate_splits


def test_single_uncategorized_split():
    total = validate_splits([(None, 42.10)])
    assert total == Decimal("42.10")


def test_multiple_category_splits_sum():
    total = validate_splits([(1, 88.40), (2, 31.20)])
    assert total == Decimal("119.60")


def test_empty_splits_rejected():
    with pytest.raises(ValidationError):
        validate_splits([])


def test_duplicate_category_rejected():
    with pytest.raises(ValidationError):
        validate_splits([(1, 10.0), (1, 20.0)])


def test_duplicate_uncategorized_rejected():
    with pytest.raises(ValidationError):
        validate_splits([(None, 10.0), (None, 20.0)])


def test_matches_expected_total():
    # should not raise
    validate_splits([(1, 60.0), (2, 40.0)], expected_total=100.0)


def test_mismatched_expected_total_rejected():
    with pytest.raises(ValidationError):
        validate_splits([(1, 60.0), (2, 39.0)], expected_total=100.0)


def test_negative_amounts_sum_correctly():
    total = validate_splits([(1, -30.0), (2, -20.0)], expected_total=-50.0)
    assert total == Decimal("-50.00")


def test_floating_point_rounding_does_not_false_reject():
    # classic float artifact: 0.1 + 0.2 != 0.3 in raw floats
    validate_splits([(1, 0.1), (2, 0.2)], expected_total=0.3)


def test_error_message_identifies_uncategorized_duplicate():
    with pytest.raises(ValidationError, match="uncategorized"):
        validate_splits([(None, 5.0), (None, 5.0)])


def test_error_message_identifies_category_duplicate():
    with pytest.raises(ValidationError, match="category 7"):
        validate_splits([(7, 5.0), (7, 5.0)])
