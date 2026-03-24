# Current Implementation State

This document provides a high-level overview of the features and architectural changes currently implemented and verified in the Tax-Agent project.

## 核心機能 (Core Features)

### 1. Invoice Management & Editor
- **Floating Action Footer**: Always-visible footer in the invoice editor containing specific actions (`発行・送付する`, `下書き保存`).
- **Status Control**: Backend correctly interprets and stores invoice status (`draft` or `sent`) provided by the frontend.
- **Invoice List**: Tabbed interface (Issued/Received/Drafts) with counts and full-width layout. Functional filtering and bulk actions.
- **Draft Editing**: Smooth transition into the editor with localized fade-in and loading states.

### 2. AI Intelligence (Gemini 3.1)
- **AI Chat Advisor**: Integrated into the sidebar, scoped to corporate accounting data.
- **Template Training**: AI-assisted parsing of sample invoices to generate structured HTML/CSS templates.
- **Matching Advice**: AI suggestions for reconciling bank transactions with receipts/invoices.

### 3. Document Processing
- **Firebase Storage**: Integrated for secure file uploads of receipts and received invoices.
- **Unified Approvals (Backend)**: Consistent rule-based approval workflow for both receipts and invoices using a shared evaluation service and `approval_rules` collection.
- **Unified Approval UI (Planned)**: Strategy confirmed to unify the approval flow visualization into a shared frontend component/package.

## 技術仕様 (Technical Specs)
- **Backend**: FastAPI (Python), MongoDB, Pydantic v2.
- **Frontend**: Vue.js 3, Vite, Lucide Icons, Custom CSS (Glassmorphism & Pastel theme).
- **Security**: Secret management via `.env` (excluded from Git).

## 検証済み項目 (Verified Items)
- ✅ Invoice status transition from Draft to Sent (End-to-End verified).
- ✅ Floating footer persistence and usability.
- ✅ Bulk issuance and deletion logic.
- ✅ AI-generated template rendering and editing.
