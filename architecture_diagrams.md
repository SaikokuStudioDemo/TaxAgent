# Architecture Diagrams (Mermaid)

This document contains Mermaid diagrams that can be imported into draw.io.
To import into draw.io: `Arrange > Insert > Advanced > Mermaid...`

## 1. Database Schema (ER Diagram)

```mermaid
erDiagram
    CORPORATES ||--o{ EMPLOYEES : "has"
    CORPORATES ||--o{ RECEIPTS : "owns"
    CORPORATES ||--o{ INVOICES : "owns"
    CORPORATES ||--o{ TRANSACTIONS : "imports"
    CORPORATES ||--o{ APPROVAL_RULES : "defines"
    
    EMPLOYEES ||--o{ RECEIPTS : "submits"
    EMPLOYEES ||--o{ APPROVAL_EVENTS : "approves"
    
    RECEIPTS ||--o{ APPROVAL_EVENTS : "tracked_by"
    INVOICES ||--o{ APPROVAL_EVENTS : "tracked_by"
    
    TRANSACTIONS ||--o{ MATCHES : "part_of"
    RECEIPTS ||--o{ MATCHES : "matched_to"
    INVOICES ||--o{ MATCHES : "matched_to"

    CORPORATES {
        string _id PK
        string firebase_uid
        string corporateType "tax_firm | corporate"
        string planId
        int monthlyFee
    }

    EMPLOYEES {
        string _id PK
        string firebase_uid
        string corporate_id FK
        string role
        json permissions
        string departmentId
    }

    RECEIPTS {
        string _id PK
        string corporate_id FK
        string submitted_by FK
        string date "YYYY-MM-DD"
        int amount
        int tax_rate
        string payee
        string category
        string approval_status "pending | approved | rejected"
        string reconciliation_status "unreconciled | reconciled"
        string approval_rule_id FK
    }

    INVOICES {
        string _id PK
        string corporate_id FK
        string created_by FK
        string document_type "issued | received"
        string client_name
        string issue_date
        string due_date
        int total_amount
        string approval_status "draft | pending | approved | rejected"
        string delivery_status "unsent | sent"
    }

    TRANSACTIONS {
        string _id PK
        string corporate_id FK
        string source_type "bank | card"
        string transaction_date
        string description
        int amount
        string status "unmatched | matched"
    }

    APPROVAL_RULES {
        string _id PK
        string corporate_id FK
        string name
        string applies_to "receipt | invoice..."
        json conditions
        json steps
        boolean active
    }

    APPROVAL_EVENTS {
        string _id PK
        string corporate_id FK
        string document_id FK
        string document_type
        int step
        string approver_id FK
        string action "approved | rejected | returned"
        string comment
    }

    MATCHES {
        string _id PK
        string corporate_id FK
        string match_type "receipt | invoice"
        list transaction_ids
        list document_ids
        int difference
        string matched_by "ai | manual"
    }
```

## 2. Process Map: Receipt/Invoice Approval to Reconciliation

```mermaid
graph TD
    A[Upload Receipt/Invoice] --> B{OCR/AI Extraction}
    B --> C[Draft Created]
    C --> D[Submit for Approval]
    D --> E{Trigger Approval Rules}
    
    E -- Matched --> F[Approval Workflow Starts]
    E -- No Rule --> G[Auto-Approved]
    
    F --> H[Step 1: Approver Notification]
    H --> I{Approver Action}
    I -- Approved --> J{Last Step?}
    I -- Rejected --> K[Return to Submitter]
    
    J -- No --> L[Next Step Approver]
    L --> H
    J -- Yes --> G
    
    G --> M[Final Approved State]
    M --> N[Reconciliation / Matching]
    
    P[Import Bank/Card Transactions] --> Q[Transaction List]
    
    N --> R{AI Matching Engine}
    Q --> R
    
    R -- Auto-Match --> S[Matched & Journal Entry Generated]
    R -- Manual Review --> T[User Reconciles Manually]
    T --> S
```

## 3. API / UI Interaction Flow (Sequence Diagram)

```mermaid
sequenceDiagram
    participant User as User (Frontend)
    participant API as Backend API (FastAPI)
    participant DB as Database (MongoDB)
    participant FS as Firebase Storage / Auth

    User->>User: Select Files (PDF/IMG)
    User->>FS: Upload Original File
    FS-->>User: File URL

    User->>API: POST /receipts (with File URL)
    API->>API: Evaluate Approval Rules
    API->>DB: Save Receipt (status: pending)
    API-->>User: Response (includes approval_steps)

    Note over User, API: Approval Process
    API->>API: Trigger Notifications
    
    User->>API: PATCH /approvals/action (Approve/Reject)
    API->>DB: Update ApprovalHistory & current_step
    API-->>User: Success (Updated Status)

    Note over User, API: Matching Process
    User->>API: GET /transactions
    API->>DB: Fetch Transactions
    API-->>User: Transaction List

    User->>API: POST /matches
    API->>DB: Link Transaction & Document IDs
    API->>DB: Set status: reconciled
    API-->>User: Success (Match Record Created)
```
