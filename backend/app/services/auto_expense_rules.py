"""
Auto Expense Rules
領収書不要で自動マッチング処理できる取引のルール定義。
インポート時に transaction の description と source_type を照合し、
一致した場合は matches コレクションに system マッチとして保存する。

フェーズ2（税理士管理画面）実装時に corporate_auto_rules コレクションへの
フォールバックロジックをここに追加する。
"""
from typing import Optional

AUTO_EXPENSE_RULES = [
    {
        "key": "bank_transfer_fee",
        "name": "振込手数料",
        "source_type": ["bank", "card"],
        "keywords": ["振込手数料", "テレフォンバンキング手数料"],
        "account_subject": "支払手数料",
        "tax_division": "対象外",
    },
    {
        "key": "etc_toll",
        "name": "ETC通行料",
        "source_type": "card",
        "keywords": ["ＥＴＣ", "ETC"],
        "account_subject": "旅費交通費",
        "tax_division": "課税仕入 10%",
    },
    {
        "key": "interest_payment",
        "name": "利息",
        "source_type": ["bank", "card"],
        "keywords": ["利息"],
        "account_subject": "支払利息",
        "tax_division": "対象外",
    },
]


CASH_DETECTION_RULES = [
    {
        "key": "cash_withdrawal",
        "name": "現金引き出し",
        "source_type": "bank",
        "transaction_type": "debit",
        "cash_direction": "income",
        "keywords": [
            "現金引出", "ＡＴＭ引出", "ATM引出", "現金出金",
            "ATM出金", "ATM入金",
            "EネットATM", "セブンATM", "ゆうちょATM",
            "ATM", "ＡＴＭ", "引出し",
        ],
        "category": "現金",
    },
    {
        "key": "cash_deposit",
        "name": "現金入金",
        "source_type": "bank",
        "transaction_type": "credit",
        "cash_direction": "expense",
        "keywords": [
            "現金入金", "ＡＴＭ入金", "ATM入金",
            "EネットATM", "セブンATM", "ゆうちょATM",
            "ATM", "ＡＴＭ",
        ],
        "category": "現金",
    },
]


def match_cash_transaction(transaction: dict) -> Optional[dict]:
    source_type = transaction.get("source_type", "")
    description = transaction.get("description", "").lower()
    transaction_type = transaction.get("transaction_type", "")

    for rule in CASH_DETECTION_RULES:
        if rule["source_type"] != source_type:
            continue
        if rule.get("transaction_type") and rule["transaction_type"] != transaction_type:
            continue
        for keyword in rule["keywords"]:
            if keyword.lower() in description:
                return rule
    return None


def match_auto_expense(transaction: dict) -> Optional[dict]:
    """
    transactionがAUTO_EXPENSE_RULESのいずれかに一致するか照合する。
    一致した場合はルールdictを返す。一致しない場合はNoneを返す。

    照合条件:
    - transaction["source_type"] がルールの source_type と一致
    - transaction["description"] がルールの keywords のいずれかを含む（大文字小文字・全角半角を考慮）
    """
    source_type = transaction.get("source_type", "")
    description = transaction.get("description", "").lower()

    for rule in AUTO_EXPENSE_RULES:
        rule_source = rule["source_type"]
        if isinstance(rule_source, list):
            if source_type not in rule_source:
                continue
        else:
            if rule_source != source_type:
                continue
        for keyword in rule["keywords"]:
            if keyword.lower() in description:
                return rule
    return None
