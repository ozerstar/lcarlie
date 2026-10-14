"""Interactively rotate the Jarvis web operator password on the server."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path("/opt/lcarlie/jarvis-phase2")
sys.path.insert(0, str(PROJECT / "webconsole"))
import auth  # noqa: E402


def main() -> int:
    if os.geteuid() != 0 or not sys.stdin.isatty():
        print("Run as root in an interactive SSH terminal.", file=sys.stderr)
        return 1
    account = auth.load_account()
    if not account:
        print("Operator account not found.", file=sys.stderr)
        return 1

    username = account["username"]
    print(f"Changing Jarvis web panel password for {username}.")
    password = getpass.getpass("New password (at least 6 characters): ")
    confirmation = getpass.getpass("Repeat new password: ")
    if len(password) < 6 or password != confirmation:
        print("Password too short or confirmation does not match.", file=sys.stderr)
        return 1

    auth_file = auth.AUTH_FILE
    backup = auth_file.with_name(f"auth.json.backup-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
    shutil.copy2(auth_file, backup)
    os.chmod(backup, 0o600)
    password_hash, salt = auth.hash_password(password)
    updated = {**account, "password_hash": password_hash, "salt": salt,
               "password_changed_at": time.time()}
    descriptor, temporary_path = tempfile.mkstemp(prefix=".auth-", dir=auth_file.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(updated, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, auth_file)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)

    subprocess.run(["systemctl", "restart", "jarvis-web"], check=True)
    subprocess.run(["systemctl", "is-active", "--quiet", "jarvis-web"], check=True)
    if not auth.verify_password(password, auth.load_account()["password_hash"],
                                auth.load_account()["salt"]):
        raise RuntimeError("Password verification failed")
    print("Password changed. Existing web sessions were ended by service restart.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
