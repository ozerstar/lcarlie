BEGIN;
ALTER TABLE core.jarvis_expense_document
    ADD COLUMN related_document_id text;
ALTER TABLE core.jarvis_expense_document
    ADD CONSTRAINT jarvis_expense_receipt_link CHECK
    (related_document_id IS NULL OR (kind='receipt' AND related_document_id<>document_id));
CREATE UNIQUE INDEX jarvis_expense_owner_document_id
    ON core.jarvis_expense_document(owner,document_id);
CREATE UNIQUE INDEX jarvis_expense_one_receipt_per_invoice
    ON core.jarvis_expense_document(owner,related_document_id)
    WHERE related_document_id IS NOT NULL;
ALTER TABLE core.jarvis_expense_document
    ADD CONSTRAINT jarvis_expense_related_owner_fk
    FOREIGN KEY (owner,related_document_id)
    REFERENCES core.jarvis_expense_document(owner,document_id);
GRANT UPDATE (related_document_id) ON core.jarvis_expense_document TO jarvis_web;

ALTER TABLE core.jarvis_expense_dispatch
    DROP CONSTRAINT jarvis_expense_dispatch_status_check;
ALTER TABLE core.jarvis_expense_dispatch
    ADD CONSTRAINT jarvis_expense_dispatch_status_check
    CHECK (status IN ('sending','sent','failed','retry_requested'));
GRANT UPDATE (package_sha256,document_count)
    ON core.jarvis_expense_dispatch TO jarvis_web;
COMMIT;
