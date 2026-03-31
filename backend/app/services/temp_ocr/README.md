# 暫定OCRサービス

⚠️ このディレクトリは暫定実装です。
本番OCR機能（別チーム開発）の実装完了後、このディレクトリを削除し、
`invoice_service.py` / `receipt_service.py` の呼び出し先を差し替えてください。

## 削除手順

1. このディレクトリを削除
2. `backend/app/api/routes/invoices.py` の `temp_ocr` インポートを削除
3. 本番OCRサービスのエンドポイントに差し替え
