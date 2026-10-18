"""INR is stored as integer paise and only formatted for display (requirement R23)."""

import pytest

from app.money import format_inr


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (2500000, "₹25,000"),
        (1500000, "₹15,000"),
        (12500000, "₹1,25,000"),
        (1234567800, "₹1,23,45,678"),
        (1550, "₹15.50"),
        (99, "₹0.99"),
        (0, "₹0"),
    ],
)
def test_indian_grouping(paise, text):
    assert format_inr(paise) == text


def test_negative_amounts_are_rejected():
    with pytest.raises(ValueError):
        format_inr(-1)


@pytest.mark.parametrize("bad", [1.5, "2500000", True, None])
def test_non_integer_amounts_are_rejected(bad):
    with pytest.raises(TypeError):
        format_inr(bad)
