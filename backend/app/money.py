"""INR amounts are integer paise everywhere; strings exist only for display (requirement R23)."""

from __future__ import annotations


def _group_indian(rupees: int) -> str:
    digits = str(rupees)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def format_inr(paise: int) -> str:
    """₹ with Indian digit grouping, e.g. 12500000 paise -> '₹1,25,000'."""
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise TypeError(f"amount must be integer paise, got {type(paise).__name__}")
    if paise < 0:
        raise ValueError("amount must not be negative")
    rupees, rem = divmod(paise, 100)
    text = "₹" + _group_indian(rupees)
    return f"{text}.{rem:02d}" if rem else text
