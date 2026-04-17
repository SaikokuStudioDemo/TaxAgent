"""
全銀フォーマット出力サービス。
承認済みの受領請求書（received）データを
全銀フォーマット（固定長テキスト・1行120バイト）で出力する。
文字コードは Shift-JIS。
"""
import logging
from datetime import datetime
from typing import Optional

from app.db.mongodb import get_database

logger = logging.getLogger(__name__)

# 全銀フォーマット レコード区分定数
ZENGIN_HEADER_CODE  = "1"
ZENGIN_DATA_CODE    = "2"
ZENGIN_TRAILER_CODE = "8"
ZENGIN_END_CODE     = "9"

ZENGIN_RECORD_LENGTH = 120


def _pad_right(s: str, length: int, char: str = " ") -> str:
    """右パディング（文字列用）。超過分は切り捨て。"""
    return str(s)[:length].ljust(length, char)


def _pad_left(s: str, length: int, char: str = "0") -> str:
    """左パディング（数値用）。超過分は切り捨て。"""
    return str(s)[:length].rjust(length, char)


def _to_zengin_kana(s: str) -> str:
    """文字列を全銀フォーマット用半角カナに変換する。濁音・半濁音にも対応。"""
    zen_to_han = {
        # 清音
        'ア': 'ｱ', 'イ': 'ｲ', 'ウ': 'ｳ', 'エ': 'ｴ', 'オ': 'ｵ',
        'カ': 'ｶ', 'キ': 'ｷ', 'ク': 'ｸ', 'ケ': 'ｹ', 'コ': 'ｺ',
        'サ': 'ｻ', 'シ': 'ｼ', 'ス': 'ｽ', 'セ': 'ｾ', 'ソ': 'ｿ',
        'タ': 'ﾀ', 'チ': 'ﾁ', 'ツ': 'ﾂ', 'テ': 'ﾃ', 'ト': 'ﾄ',
        'ナ': 'ﾅ', 'ニ': 'ﾆ', 'ヌ': 'ﾇ', 'ネ': 'ﾈ', 'ノ': 'ﾉ',
        'ハ': 'ﾊ', 'ヒ': 'ﾋ', 'フ': 'ﾌ', 'ヘ': 'ﾍ', 'ホ': 'ﾎ',
        'マ': 'ﾏ', 'ミ': 'ﾐ', 'ム': 'ﾑ', 'メ': 'ﾒ', 'モ': 'ﾓ',
        'ヤ': 'ﾔ', 'ユ': 'ﾕ', 'ヨ': 'ﾖ',
        'ラ': 'ﾗ', 'リ': 'ﾘ', 'ル': 'ﾙ', 'レ': 'ﾚ', 'ロ': 'ﾛ',
        'ワ': 'ﾜ', 'ヲ': 'ｦ', 'ン': 'ﾝ',
        # 小文字
        'ァ': 'ｧ', 'ィ': 'ｨ', 'ゥ': 'ｩ', 'ェ': 'ｪ', 'ォ': 'ｫ',
        'ッ': 'ｯ', 'ャ': 'ｬ', 'ュ': 'ｭ', 'ョ': 'ｮ',
        # 濁音（2文字 = 清音 + ﾞ）
        'ガ': 'ｶﾞ', 'ギ': 'ｷﾞ', 'グ': 'ｸﾞ', 'ゲ': 'ｹﾞ', 'ゴ': 'ｺﾞ',
        'ザ': 'ｻﾞ', 'ジ': 'ｼﾞ', 'ズ': 'ｽﾞ', 'ゼ': 'ｾﾞ', 'ゾ': 'ｿﾞ',
        'ダ': 'ﾀﾞ', 'ヂ': 'ﾁﾞ', 'ヅ': 'ﾂﾞ', 'デ': 'ﾃﾞ', 'ド': 'ﾄﾞ',
        'バ': 'ﾊﾞ', 'ビ': 'ﾋﾞ', 'ブ': 'ﾌﾞ', 'ベ': 'ﾍﾞ', 'ボ': 'ﾎﾞ',
        'ヴ': 'ｳﾞ',
        # 半濁音（2文字 = 清音 + ﾟ）
        'パ': 'ﾊﾟ', 'ピ': 'ﾋﾟ', 'プ': 'ﾌﾟ', 'ペ': 'ﾍﾟ', 'ポ': 'ﾎﾟ',
        # 記号
        '゛': 'ﾞ', '゜': 'ﾟ', '　': ' ',
        '（': '(', '）': ')', '－': '-', '．': '.',
    }
    result = "".join(zen_to_han.get(ch, ch) for ch in s)
    return result.upper()


async def export_zengin(
    corporate_id: str,
    fiscal_period: Optional[str] = None,
    company_name: str = "",
    bank_code: str = "",
    branch_code: str = "",
    account_type: str = "1",
    account_number: str = "",
) -> str:
    """
    全銀フォーマットの固定長テキストを返す。
    対象：承認済みの受領請求書（document_type="received"）。
    データなしの場合は空文字を返す。
    """
    db = get_database()

    query = {
        "corporate_id": corporate_id,
        "document_type": "received",
        "approval_status": "approved",
        "reconciliation_status": {"$ne": "reconciled"},
    }
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    invoices = await db["invoices"].find(query).to_list(length=10000)
    if not invoices:
        return ""

    now = datetime.utcnow()
    transfer_date = now.strftime("%m%d")
    total_amount = sum(int(inv.get("total_amount") or 0) for inv in invoices)
    total_count = len(invoices)

    lines = []

    # ── ヘッダーレコード（120文字固定）─────────────────────────────────
    # 区分(1) + 種別(2) + コード区分(1) + 依頼人コード(10) + 依頼人名(40)
    # + 振込日(4) + 仕向銀行番号(4) + 仕向銀行名(15) + 仕向支店番号(3)
    # + 仕向支店名(15) + 預金種目(1) + 口座番号(7) + ダミー(17) = 120
    header = (
        ZENGIN_HEADER_CODE
        + "21"
        + "0"
        + _pad_right("", 10)                          # 依頼人コード 10桁
        + _pad_right(_to_zengin_kana(company_name), 40)
        + transfer_date
        + _pad_left(bank_code, 4)
        + _pad_right("", 15)
        + _pad_left(branch_code, 3)
        + _pad_right("", 15)
        + account_type
        + _pad_left(account_number, 7)
        + _pad_right("", 17)
    )
    lines.append(header[:ZENGIN_RECORD_LENGTH])

    # ── データレコード（請求書ごと）──────────────────────────────────────
    for inv in invoices:
        vendor_bank_code    = str(inv.get("vendor_bank_code", "0000"))
        vendor_branch_code  = str(inv.get("vendor_branch_code", "000"))
        vendor_acct_type    = str(inv.get("vendor_account_type", "1"))
        vendor_acct_number  = str(inv.get("vendor_account_number", "0000000"))
        vendor_name         = inv.get("vendor_name", "")
        amount              = int(inv.get("total_amount") or 0)

        # 区分(1) + 受取銀行番号(4) + 受取銀行名(15) + 受取支店番号(3)
        # + 受取支店名(15) + 手順(1) + 預金種目(1) + 口座番号(7) + 受取人名(30)
        # + 振込金額(10) + 新規コード(1) + EDI情報(10) + ダミー(22) = 120
        data = (
            ZENGIN_DATA_CODE
            + _pad_left(vendor_bank_code, 4)
            + _pad_right("", 15)
            + _pad_left(vendor_branch_code, 3)
            + _pad_right("", 15)
            + "1"
            + vendor_acct_type
            + _pad_left(vendor_acct_number, 7)
            + _pad_right(_to_zengin_kana(vendor_name), 30)
            + _pad_left(str(amount), 10)
            + "0"
            + _pad_right("", 10)   # EDI情報 10桁
            + _pad_right("", 22)   # ダミー 22桁（17→22 に修正）
        )
        lines.append(data[:ZENGIN_RECORD_LENGTH])

    # ── トレーラーレコード ────────────────────────────────────────────────
    trailer = (
        ZENGIN_TRAILER_CODE
        + _pad_left(str(total_count), 6)
        + _pad_left(str(total_amount), 12)
        + _pad_right("", 101)
    )
    lines.append(trailer[:ZENGIN_RECORD_LENGTH])

    # ── エンドレコード ────────────────────────────────────────────────────
    end = ZENGIN_END_CODE + _pad_right("", 119)
    lines.append(end[:ZENGIN_RECORD_LENGTH])

    return "\r\n".join(lines)
