import math


def calc_tax_from_inclusive(amount: int, tax_rate: int) -> int:
    """
    税込金額から消費税額を逆算する（四捨五入）。
    tax_rate は int（10・8・0）。
    """
    if tax_rate == 0:
        return 0
    return round(amount * tax_rate / (100 + tax_rate))


def calc_tax_from_exclusive(amount: int, tax_rate: int) -> int:
    """
    税抜金額から消費税額を直算する（切り捨て）。
    日本の消費税法の原則に従う。
    """
    if tax_rate == 0:
        return 0
    return math.floor(amount * tax_rate / 100)


def calc_inclusive_from_exclusive(amount: int, tax_rate: int) -> int:
    """
    税抜金額から税込金額を計算する（切り捨て）。
    """
    return amount + calc_tax_from_exclusive(amount, tax_rate)
