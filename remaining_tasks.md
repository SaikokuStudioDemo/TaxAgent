# Remaining Tasks

This document tracks the outstanding requirements and future improvements for the Tax-Agent project.

## 優先度：高 (High Priority)
- [x] ~~**Approval UI Unification**~~: 共有 `ApprovalStepper` コンポーネントを作成し、領収書・請求書の両方の承認フロー（DetailModal、CreatePage、UploadPage）で使用。完了済み。
- [x] ~~**Navigation UX Alignment**~~: 下書き編集時のfade-inトランジションを統一。完了済み。
- [x] ~~**Approval Page Layout Standardization**~~: 領収書・請求書承認ページのUI、タブレイアウト、検索フィルター、stickyカラムの統一。完了済み。
- [ ] **承認付き請求書の送信プロセス改善**: 承認が必要な請求書を送信する際のUXフロー整理。現在は承認必要時に `draft` ステータスで保存されるが、ユーザーに「承認待ちで送信は保留」であることを明確に伝えるUI設計が必要。

## 優先度：中 (Medium Priority)
- ~~**Template Gallery Expansion**~~: 不要と判断（業者ごとに異なるため、初期設定での登録フローで対応）
- ~~**Receipt OCR Refinement**~~: 別チームが担当のため対象外
- [ ] **コードリファクタリング**: `refactoring_audit.md` に記載の重複コード整理（`_serialize` 統合、`formatAmount` 統一、CRUD Composable共通化、認証ボイラープレート削減など）。
- [x] ~~**useCompanyProfiles API連携**~~: モックデータを削除し、api.get/post/patch/deleteで実API接続に変更済み。
- [ ] **Mobile Responsiveness Check**: フローティングフッターやテーブルのモバイル表示確認。

## フロントエンド完成後に実施
- [ ] **全体洗い直し・漏れ確認**: フロントエンドのUI調整完了後に、バックエンドとの結合を含めた全体レビューを実施する。

## 管理者機能（Admin UI完成後に対応）
- [ ] **Law Agent URL の管理画面移行**: 現在 `.env` の `LAW_AGENT_URL` で管理している外部法令AIエージェントのURLを、Admin専用の `system_settings` コレクションに移行し、管理画面から設定できるようにする。Admin認証・権限管理の実装が前提。

## メンテナンス & クリーンアップ (Maintenance)
- [ ] **Ongoing Artifact Cleanup**: Periodically move old step/test logs to the `/archive` directory to keep the workspace efficient.
- [ ] **Secret Audit**: Regularly verify that no new environment variables have been committed to the repository.

## 優先度：低（要望ベースで対応）
- [ ] **マッチングページの承認ステータスフィルター**: 
  マッチングページ（領収書・請求書）に承認済み／未承認で
  絞り込めるフィルターを追加する。
  現状は承認状態に関わらず全件表示する仕様で問題ないが、
  ユーザーから要望があれば対応する。
  実装はfrontendのfetchAndMapReceipts/fetchAndMapInvoicesに
  approval_statusフィルターを追加するだけ。

