"""inventory 표시용 template filter. (v0.1.1)

표시 전용이며 DB 저장/검증 로직과 무관하다.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name="days_since")
def days_since(value, today):
    """value(date) 부터 today(date) 까지 경과일. 표시 전용. (v0.2.1)"""
    try:
        return (today - value).days
    except (TypeError, AttributeError):
        return ""


@register.filter(name="qty")
def qty(value):
    """수량(Decimal) 표시에서 불필요한 0 을 제거한다.

    10.000 → 10, 10.500 → 10.5, 10.250 → 10.25, 10.125 → 10.125
    값이 비었거나 숫자가 아니면 원본을 그대로 반환한다. (표시 전용)
    """
    if value is None or value == "":
        return value
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    s = format(d, "f")  # 고정소수점 문자열 (예: '10.000')
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s
