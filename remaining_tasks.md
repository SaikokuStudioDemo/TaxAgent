# Remaining Tasks

This document tracks the outstanding requirements and future improvements for the Tax-Agent project.

## 優先度：高 (High Priority)
- [ ] **Approval UI Unification (In Progress)**: Extract approval flow logic into a reusable `ApprovalFlow` component for both Receipts and Invoices.
- [ ] **Navigation UX Alignment**: Ensure that "Edit Draft" uses the same localized fade-in transition as the "New Invoice" path.
- [ ] **Mobile Responsiveness Check**: Verify that the newly implemented floating footer performs well on mobile viewport sizes.

## 優先度：中 (Medium Priority)
- ~~**Template Gallery Expansion**~~: 不要と判断（業者ごとに異なるため、初期設定での登録フローで対応）
- ~~**Receipt OCR Refinement**~~: 別チームが担当のため対象外

## フロントエンド完成後に実施
- [ ] **全体洗い直し・漏れ確認**: フロントエンドのUI調整（承認フロー等）完了後に、バックエンドとの結合を含めた全体レビューを実施する。

## 管理者機能（Admin UI完成後に対応）
- [ ] **Law Agent URL の管理画面移行**: 現在 `.env` の `LAW_AGENT_URL` で管理している外部法令AIエージェントのURLを、Admin専用の `system_settings` コレクションに移行し、管理画面から設定できるようにする。Admin認証・権限管理の実装が前提。

## メンテナンス & クリーンアップ (Maintenance)
- [ ] **Ongoing Artifact Cleanup**: Periodically move old step/test logs to the `/archive` directory to keep the workspace efficient.
- [ ] **Secret Audit**: Regularly verify that no new environment variables have been committed to the repository.
