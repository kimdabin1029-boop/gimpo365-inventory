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


def _strip_zeros(value):
    """Decimal 문자열에서 불필요한 뒤쪽 0 을 제거한 문자열(콤마 없음). 실패 시 None."""
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    s = format(d, "f")  # 고정소수점 문자열 (예: '10.000')
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _with_commas(s):
    """정수부에 1,000 단위 콤마를 넣는다. (소수부/부호 유지)"""
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        int_part, dec = s.split(".", 1)
    else:
        int_part, dec = s, None
    try:
        int_part = f"{int(int_part):,}"
    except ValueError:
        return ("-" + s) if neg else s
    result = int_part + ("." + dec if dec else "")
    return ("-" + result) if neg else result


@register.filter(name="plain")
def plain(value):
    """수량 표시(콤마 없음). input value/max 등 콤마가 들어가면 안 되는 곳에 사용.

    10.000 → 10, 10.500 → 10.5, 1000.000 → 1000. 실패 시 원본 반환. (표시 전용)
    """
    s = _strip_zeros(value)
    return value if s is None else s


@register.filter(name="qty")
def qty(value):
    """수량 표시. 불필요한 0 제거 + 1,000 단위 콤마. (표시 전용)

    1000.000 → 1,000 · 1000.5 → 1,000.5 · 1000.125 → 1,000.125 · 12000 → 12,000
    값이 비었거나 숫자가 아니면 원본을 그대로 반환한다.
    주의: HTML input value/max 에는 콤마가 들어가면 안 되므로 plain 필터를 사용한다.
    """
    s = _strip_zeros(value)
    return value if s is None else _with_commas(s)


@register.filter(name="money")
def money(value):
    """단가/금액 표시. 1,000 단위 콤마 + 불필요한 0 제거. (표시 전용)

    12000 → 12,000 · 1234567 → 1,234,567 · 1500.50 → 1,500.5
    """
    return qty(value)
