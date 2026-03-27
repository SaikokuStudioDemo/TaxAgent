# Current Implementation State

This document provides a high-level overview of the features and architectural changes currently implemented and verified in the Tax-Agent project.

## 核心機能 (Core Features)

### 1. Invoice Management & Editor
- **Floating Action Footer**: Always-visible footer in the invoice editor containing specific actions (`発行・送付する`, `下書き保存`).
- **Status Control**: Backend correctly interprets and stores invoice status (`draft` or `sent`) provided by the frontend.
- **Invoice List**: Tabbed interface (Issued/Received/Drafts) with counts, full-width layout, and sticky action columns. Functional filtering and bulk actions.
- **Draft Editing**: Smooth transition into the editor with localized fade-in and loading states.
- **Received Invoice Upload**: AI-assisted OCR extraction and manual entry for received invoices.

### 2. Approval Workflow (Receipts & Invoices)
- **Unified Approvals (Backend)**: Consistent rule-based approval workflow for both receipts and invoices using a shared evaluation service and `approval_rules` collection.
- **Approval Types Consolidation**: Shared `approvalTypes.ts` for consistent `ApprovalHistory`, `ReceiptItem`, and `InvoiceItem` definitions across all views and modals.
- **Shared ApprovalStepper Component**: Reusable `ApprovalStepper.vue` used in ReceiptDetailModal, InvoiceDetailModal, InvoiceCreatePage, and ReceiptUploadPage.
- **Approval Dashboard (Receipts)**: Full-width tab layout with status tabs (あなたの承認待ち / 全社未承認 / 承認済 / 差戻し).
- **Pending-for-me Integration**: The "Your Pending" tab correctly filters records where the current user is the specific approver using the backend API.
- **Sticky Columns**: Status and Action columns remain visible during horizontal scrolling on both approval pages.
- **Multi-step Approval**: Support for hierarchical approval steps, extra approver addition, and optimistic locking for concurrent approvals.

### 3. Matching (Reconciliation)
- **Unified Transactions**: Renamed `bank_transactions` to `transactions` to include both bank and credit card data in a single unified pipeline.
- **Receipt Matching**: Match bank/card transactions to receipts with difference auto-resolution (< ¥1,000).
- **Invoice Matching**: Match bank transactions to invoices with the same reconciliation logic.
- **Journal Entry Generation**: Auto-generated journal entries for small differences (雑損失/雑収入).

### 4. AI Intelligence (Gemini)
- **AI Chat Advisor**: Integrated into the sidebar, scoped to corporate accounting data.
- **Template Training**: AI-assisted parsing of sample invoices to generate structured HTML/CSS templates.
- **Matching Advice**: AI suggestions for reconciling bank transactions with receipts/invoices.

### 5. Document Processing
- **Firebase Storage**: Integrated for secure file uploads of receipts and received invoices.

## 技術仕様 (Technical Specs)
- **Backend**: FastAPI (Python), MongoDB, Pydantic v2.
- **Frontend**: Vue.js 3, Vite, Lucide Icons, Tailwind CSS.
- **Security**: Secret management via `.env` (excluded from Git).

### 6. User & Organization Management
- **User Management**: Employee invite/edit/delete with role, permissions, department/group assignment. PATCH on field change (no debounced watch).
- **Department Master**: DB-backed departments API (`/departments`) with groups. OrganizationPage fully API-connected.
- **DEV_AUTH_TOKEN**: Dev login (`test-token` / `tax-test-token`) unified with prod code path — no separate bypass logic.

### 7. Company & Client Data
- **Company Profiles**: Self-owned profile management via `/company-profiles` API.
- **Clients**: Full client records with department, contact_person, postal_code, internal_notes fields.
- **Bank Accounts**: `/bank-accounts` — supports `owner_type: "corporate"|"client"`, is_default per scope, 全銀API lookup (bank.teraren.com) with 24h memory cache.
- **Invoice Bank Account**: Sender profile drives bank account selection in invoice create page.

## 検証済み項目 (Verified Items)
- ✅ Invoice status transition from Draft to Sent (End-to-End verified).
- ✅ Floating footer persistence and usability.
- ✅ Bulk issuance and deletion logic.
- ✅ AI-generated template rendering and editing.
- ✅ Approval page UI standardization (receipts & invoices).
- ✅ Sticky column implementation for approval tables.
- ✅ Sidebar navigation consistency (請求書承認状況).
- ✅ Invoice list responsive table with sticky action column.
- ✅ DEV_BYPASS_AUTH廃止 → DEV_AUTH_TOKEN統一 (開発/本番同一コードパス).
- ✅ Department dropdown PATCH on change (watch廃止).
- ✅ Bank accounts with 全銀API lookup (zengin routes before /{id} to avoid conflict).
- ✅ GET /clients/{id} embeds bank_accounts array.
