"""SQLite şeması ve bağlantı."""
import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, job TEXT, source TEXT, started_at TEXT);
CREATE TABLE IF NOT EXISTS source_health(
  id INTEGER PRIMARY KEY, run_id TEXT, source TEXT, ok INTEGER, error TEXT, checked_at TEXT);
CREATE TABLE IF NOT EXISTS brands(
  id INTEGER PRIMARY KEY, name TEXT, norm_name TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'unqualified',  -- candidate|active|passive|rejected|filtered|unqualified
  first_seen TEXT, last_seen TEXT, approved_at TEXT, reported_at TEXT,
  status_reason TEXT, score INTEGER DEFAULT 0, detail TEXT DEFAULT '{}',
  website TEXT, instagram TEXT, trendyol_url TEXT, origin TEXT,
  first_seen_hint TEXT, texts TEXT DEFAULT '[]', quiet_months INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY, brand_id INTEGER, name TEXT, norm_name TEXT, category TEXT,
  first_seen TEXT, last_seen TEXT, UNIQUE(brand_id, norm_name));
CREATE TABLE IF NOT EXISTS observations(
  id INTEGER PRIMARY KEY, brand_id INTEGER, product_id INTEGER, kind TEXT,
  value_num REAL, value_text TEXT, source_url TEXT NOT NULL, fetched_at TEXT NOT NULL,
  run_id TEXT, excerpt TEXT, verified INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_obs ON observations(brand_id, product_id, kind, fetched_at);
CREATE TABLE IF NOT EXISTS pending_changes(
  id INTEGER PRIMARY KEY, brand_id INTEGER, product_id INTEGER, kind TEXT,
  old_value REAL, new_value REAL, first_obs_id INTEGER, first_run_id TEXT,
  created_at TEXT, status TEXT DEFAULT 'pending', resolved_at TEXT);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY, created_at TEXT, level TEXT, text TEXT, sources TEXT, briefed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY, created_at TEXT, channel TEXT, recipient TEXT, subject TEXT, body TEXT,
  needs_approval INTEGER, status TEXT, decided_at TEXT, sent_at TEXT, ref TEXT);
CREATE TABLE IF NOT EXISTS snapshots(
  id INTEGER PRIMARY KEY, brand_id INTEGER, month TEXT, data TEXT, UNIQUE(brand_id, month));
CREATE TABLE IF NOT EXISTS leads(
  id INTEGER PRIMARY KEY, place_id TEXT UNIQUE, name TEXT, type TEXT, address TEXT, phone TEXT,
  website TEXT, rating REAL, source_url TEXT, query TEXT, found_at TEXT, status TEXT DEFAULT 'new', briefed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reg_pages(
  url TEXT PRIMARY KEY, last_hash TEXT, last_text TEXT, last_checked TEXT, last_changed TEXT);
CREATE TABLE IF NOT EXISTS reg_changes(
  id INTEGER PRIMARY KEY, url TEXT, found_at TEXT, lines TEXT, briefed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS keywords(kw TEXT PRIMARY KEY, kind TEXT, added_at TEXT);
CREATE TABLE IF NOT EXISTS content_drafts(
  id INTEGER PRIMARY KEY, week TEXT, day TEXT, channel TEXT, product TEXT, text TEXT,
  check_result TEXT, status TEXT DEFAULT 'draft', created_at TEXT, briefed INTEGER DEFAULT 0);
"""


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
    conn.executescript(SCHEMA)
    return conn


def jload(s, default=None):
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default


def jdump(o):
    return json.dumps(o, ensure_ascii=False)
