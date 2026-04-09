"""
Anonymizer Service
個人名・会社名をハッシュベースで匿名化する。
同じ名前は常に同じ匿名名に変換される（一貫性保証）。
マッピング表は backend/anonymization_map.json に保存。
"""
import hashlib
import json
from pathlib import Path

MAPPING_FILE = Path(__file__).parent.parent.parent / "anonymization_map.json"

PREFIXES = {
    "company": "テスト会社",
    "person": "テスト個人",
}

# 匿名化しないキーワード（銀行ロジックに必要なもの）
KEEP_KEYWORDS = [
    "ATM", "ＡＴＭ", "振込手数料", "テレフォンバンキング",
    "利息", "引出し", "入金", "出金", "ローソン", "セブン",
    "ゆうちょ", "ETC", "ＥＴＣ", "振込", "自動払込",
]


class Anonymizer:
    def __init__(self):
        self._map: dict = {}
        self._load()

    def _load(self):
        if MAPPING_FILE.exists():
            with open(MAPPING_FILE, encoding="utf-8") as f:
                self._map = json.load(f)

    def _save(self):
        with open(MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(self._map, f, ensure_ascii=False, indent=2)

    def anonymize(self, original: str, category: str = "company") -> str:
        """
        名前を匿名化する。同じ original は常に同じ匿名名を返す。
        category: "company" | "person"
        """
        if not original or not original.strip():
            return original

        key = f"{category}:{original}"
        if key in self._map:
            return self._map[key]

        hash_id = str(
            int(hashlib.md5(original.encode()).hexdigest(), 16) % 9000 + 1000
        )
        prefix = PREFIXES.get(category, "テスト")
        anonymized = f"{prefix}{hash_id}"

        self._map[key] = anonymized
        self._map[f"reverse:{anonymized}"] = original
        self._save()

        return anonymized

    def anonymize_bank_description(self, description: str) -> str:
        """
        銀行摘要の匿名化。
        ATM・振込手数料などロジックに必要なキーワードは保持し、
        人名・会社名部分のみ匿名化する。
        """
        for kw in KEEP_KEYWORDS:
            if kw in description:
                return description
        return self.anonymize(description, "company")


anonymizer = Anonymizer()
