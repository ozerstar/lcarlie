from __future__ import annotations

import os


def memory_host() -> str | None:
    """Resolve the Company Memory transport.

    Returns None when the caller runs on the production host itself (the
    adapter then talks to the local `lcarlie-postgres` container directly),
    otherwise the SSH host alias to hop through.

    This was previously inlined in jarvis.shadow only, which left
    tests/test_live_phase2.py and scripts/benchmark_live.py hard-bound to the
    SSH alias `lcarlie` -- an alias that does not resolve *on* the server, so
    both failed with "Could not resolve hostname lcarlie" when run there.
    """
    if os.environ.get("JARVIS_MEMORY_TRANSPORT") == "local-docker":
        return None
    return os.environ.get("JARVIS_SSH_HOST", "lcarlie")
