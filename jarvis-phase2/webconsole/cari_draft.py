"""Editable cari movement drafts, kept separate from the posted ledger."""
from __future__ import annotations

import uuid

import cari
from personal_action_store import _connect


def _body(raw):
    if not isinstance(raw, dict):
        raise cari.CariError("Taslak hareketi geçersiz.")
    # Store only validated input fields; calculate again on posting.
    keys = ("kind", "date", "due_date", "reference", "note", "items", "amount",
            "payment_method", "applies_to")
    body = {key: raw[key] for key in keys if key in raw}
    cari.calculate(body)
    return body


def list_drafts(owner, account_id):
    account_id = cari._id(account_id)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT draft_id AS id,account_id,body,created_at,updated_at
            FROM core.jarvis_cari_draft WHERE owner=%s AND account_id=%s
            AND status='draft' ORDER BY created_at DESC,draft_id""", (owner, account_id))
        return {"drafts": [dict(row, created_at=str(row["created_at"]),
                                updated_at=str(row["updated_at"]),
                                preview=cari.calculate(row["body"])) for row in cur.fetchall()]}


def create(owner, account_id, raw):
    account_id = cari._id(account_id)
    body = _body(raw)
    from psycopg.types.json import Jsonb
    draft_id = uuid.uuid4().hex
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO core.jarvis_cari_draft
            (draft_id,owner,account_id,body) VALUES (%s,%s,%s,%s)""",
            (draft_id, owner, account_id, Jsonb(body)))
    return {"id": draft_id, "status": "draft"}


def update(owner, account_id, draft_id, raw):
    account_id, draft_id = cari._id(account_id), cari._id(draft_id)
    body = _body(raw)
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE core.jarvis_cari_draft SET body=%s,updated_at=clock_timestamp()
            WHERE owner=%s AND account_id=%s AND draft_id=%s AND status='draft'
            RETURNING draft_id""", (Jsonb(body), owner, account_id, draft_id))
        if not cur.fetchone():
            raise cari.CariNotFound("Düzenlenebilir taslak bulunamadı.")
    return {"id": draft_id, "status": "draft"}


def post(owner, account_id, draft_id):
    """Atomically post once; concurrent approvals return the same ledger entry."""
    account_id, draft_id = cari._id(account_id), cari._id(draft_id)
    from psycopg.types.json import Jsonb
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (owner + ':' + account_id,))
        cur.execute("""SELECT body,status,posted_entry_id FROM core.jarvis_cari_draft
            WHERE owner=%s AND account_id=%s AND draft_id=%s""",
            (owner, account_id, draft_id))
        draft = cur.fetchone()
        if not draft:
            raise cari.CariNotFound("Taslak bulunamadı.")
        if draft["status"] == "posted":
            return {"id": draft["posted_entry_id"], "reused": True}
        body = _body(draft["body"])
        payload = cari.calculate(body)
        cari._check_allocation(cur, owner, account_id, payload)
        entry_id = uuid.uuid4().hex
        cur.execute("""INSERT INTO core.jarvis_cari_entry
            (entry_id,owner,account_id,request_id,payload_hash,document_date,
             payload,signed_cents,unknown_tax)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (entry_id, owner, account_id, "draft:" + draft_id, cari._digest(payload),
             payload["date"], Jsonb(payload), payload["signed_cents"], payload["unknown_tax"]))
        cur.execute("""UPDATE core.jarvis_cari_draft
            SET status='posted',posted_entry_id=%s,updated_at=clock_timestamp()
            WHERE owner=%s AND account_id=%s AND draft_id=%s""",
            (entry_id, owner, account_id, draft_id))
    return {"id": entry_id, "reused": False}
