"""
Transaction Type Classifier
出金額・入金額・摘要から transaction_type (debit/credit) を判定する。
"""


def classify_transaction_type(
    withdrawal_amount: int,
    deposit_amount: int,
    description: str = "",
) -> str:
    """
    出金・入金の金額から transaction_type を返す。
    両方ある場合は大きい方を優先。両方0の場合は description で判定。
    """
    if withdrawal_amount > 0 and deposit_amount == 0:
        return "debit"
    if deposit_amount > 0 and withdrawal_amount == 0:
        return "credit"
    if withdrawal_amount > 0 and deposit_amount > 0:
        return "debit" if withdrawal_amount >= deposit_amount else "credit"

    # 両方0の場合は摘要で判定
    desc = description
    if any(kw in desc for kw in ["入金", "振込入", "受取", "入　金"]):
        return "credit"
    return "debit"
