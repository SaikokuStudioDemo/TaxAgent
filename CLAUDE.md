# SAIKOKU STUDIO / Tax Agent — Claude Code 運用ガイド

## プロジェクト概要
- バックエンド：Python 3.9 / FastAPI / MongoDB / Firebase Auth
- フロントエンド：Vue.js 3 / TypeScript / Tailwind CSS
- 設計ドキュメント：ナレッジベース参照

---

## 最重要ルール

### Python 3.9 対応
- `str | None` は使わない → `Optional[str]`
- `list[str]` は使わない → `List[str]`
- `from typing import Optional, List, Dict, Any` を必ず追加

### データスコープの徹底
- 全 API エンドポイントで `corporate_id` によるフィルタを徹底する
- 別法人のデータを返さないこと
- テストで必ずスコープ漏洩を確認すること

### エラーハンドリング
- 全ツール・サービスメソッドで `try/except` を使い例外を外に漏らさない
- エラーは `{"error": "メッセージ"}` 形式で返す

### DB への書き込み
- 提案系ツールは DB への書き込みを行わない
- 実行系ツールは `confirmation_required: True` を返す
- AI が確認なしに DB を変更・削除しない

### コード品質
- 同じような機能・コードを重複して作らない
- 既存のヘルパー関数（`helpers.py` 等）を再利用する
- `serialize_doc` / `build_name_map` / `get_doc_or_404` 等を活用する
- シンプルで分かりやすい構成を優先する

---

## テストの方針
- 実装後は必ず意地悪テストまでセット
- スコープ境界・エラー耐性・境界値を必ずカバー
- DB への意図しない書き込みを確認する
- 全テスト PASSED 後に次のタスクへ進む

---

## 既存実装の確認
- 実装前に必ず関連ファイルを確認する
- `helpers.py` の既存ヘルパーを使う
- `serialize_doc` / `build_name_map` / `get_doc_or_404` 等
