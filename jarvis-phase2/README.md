# JARVIS BOOTSTRAP

This package is a production-disconnected, deterministic bootstrap. It reads no
secrets, calls no provider, and executes no external action.

Run from this directory:

```powershell
python -m unittest discover -s tests -v
python -m jarvis.cli --capabilities
python -m jarvis.cli --benchmark
python -m jarvis.cli "send whatsapp message"
```

Production integration remains PROPOSED pending a reviewed DB adapter, fresh
rollback artifacts, sandbox tests, and explicit human approval.
