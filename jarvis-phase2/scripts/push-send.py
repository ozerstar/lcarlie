"""Send a fixed test push or notify the operator about new pending approvals."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pywebpush import WebPushException, webpush

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webconsole"))
import push_store  # noqa: E402
import mobile_features  # noqa: E402


def send(subscription: dict, title: str, body: str, tag: str) -> bool:
    try:
        webpush(
            subscription_info={"endpoint": subscription["endpoint"], "keys": subscription["keys"]},
            data=json.dumps({"title": title, "body": body[:150], "tag": tag}, ensure_ascii=False),
            vapid_private_key=str(push_store.PRIVATE_KEY_FILE),
            vapid_claims={"sub": "https://jarvis.lcarlie.shop"},
            ttl=3600,
            timeout=10,
        )
        return True
    except WebPushException as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status in (404, 410):
            push_store.remove(subscription["endpoint"])
        print(f"push rejected: HTTP {status or 'unknown'}", file=sys.stderr)
        return False
    except Exception:  # noqa: BLE001 - bildirim hatasi gonderici dongusunu durduramaz
        print("push delivery request failed", file=sys.stderr)
        return False


def pending_approvals() -> list[dict]:
    sql = ("BEGIN; SET SESSION AUTHORIZATION human_approver; "
           "SELECT row_to_json(x) FROM (SELECT action_id,action_type,payload FROM core.ai_get_pending_actions()) x; "
           "ROLLBACK;")
    result = subprocess.run(
        ["docker", "exec", "lcarlie-postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
         "-U", "n8n", "-d", "n8n", "-Atc", sql],
        capture_output=True, text=True, timeout=20, check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def save_seen(seen: dict) -> None:
    descriptor, temporary_path = tempfile.mkstemp(prefix=".push-seen-", dir=push_store.STATE_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(seen, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, push_store.SEEN_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def notify_new_approvals() -> None:
    subscriptions = push_store.all_subscriptions()
    if not subscriptions:
        return
    pending = pending_approvals()
    current = {str(item["action_id"]): item for item in pending}
    seen = json.loads(push_store.SEEN_FILE.read_text(encoding="utf-8")) if push_store.SEEN_FILE.exists() else {}
    for identifier, subscription in subscriptions.items():
        if identifier not in seen:
            seen[identifier] = list(current)
            continue
        delivered = set(seen[identifier])
        for action_id, proposal in current.items():
            if action_id in delivered:
                continue
            reason = str((proposal.get("payload") or {}).get("reason") or "Yeni bir öneri var.")
            external = proposal.get("action_type") in {
                "WHATSAPP_SEND_TEMPLATE", "META_CAMPAIGN_CHANGE", "PRICE_CHANGE", "WIX_PUBLISH"
            }
            title = "🔴 Jarvis · Dış işlem onayı" if external else "Jarvis · Onay bekliyor"
            if send(subscription, title, f"#{action_id} · {reason}", f"approval-{action_id}"):
                delivered.add(action_id)
        seen[identifier] = list(delivered & set(current))
    save_seen(seen)


def notify_due_reminders() -> None:
    subscriptions = push_store.all_subscriptions()
    for reminder in mobile_features.due_reminders():
        targets = {identifier: subscription for identifier, subscription in subscriptions.items()
                   if subscription.get("owner") == reminder.get("user")}
        sent = set(reminder.get("sent_to") or [])
        for identifier, subscription in targets.items():
            if identifier in sent:
                continue
            if send(subscription, "Jarvis · Hatırlatıcı", reminder["text"],
                    f"reminder-{reminder['id']}-{reminder['due_at']}"):
                mobile_features.mark_sent(reminder["id"], identifier)
                sent.add(identifier)
        if targets and set(targets).issubset(sent):
            mobile_features.advance_reminder(reminder["id"], set(targets))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--test":
        subscription = push_store.get(sys.argv[2])
        if not subscription or not send(subscription, "Jarvis test bildirimi",
                                        "Telefon bildirim bağlantısı hazır.", "jarvis-test"):
            raise SystemExit(1)
    elif len(sys.argv) == 1:
        notify_due_reminders()
        notify_new_approvals()
    else:
        raise SystemExit(2)
