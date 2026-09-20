"""L'CARLIE Jarvis Web Console -- thin API + static frontend server.

Reuses the existing Jarvis core untouched:
  jarvis.shadow.ShadowRunner   -- real chat pipeline (Phase 2C/2D, unmodified)
  jarvis.operator.OperatorSession -- real human-approver proposal boundary
  jarvis.memory.CompanyMemory  -- real Company Memory reads

This process never assumes ai_writer or human_approver as its OWN identity;
every DB call happens inside jarvis.memory / jarvis.operator, which each set
SESSION AUTHORIZATION per call exactly as already verified. This server adds
NOTHING to that boundary -- it is a browser-facing shell around it.

Binds 0.0.0.0:<port> because Caddy reaches it from inside a docker container
via the docker bridge, not loopback. Public exposure is blocked at the host
firewall (ufw allow only from the docker bridge subnet), not by this process.

Stdlib only: http.server + manual routing/sessions/CSRF/rate-limit. No new
framework, no new package install.
"""
from __future__ import annotations

import json
import os
import sys
import time
import pathlib
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
JARVIS_ROOT = HERE.parent
sys.path.insert(0, str(JARVIS_ROOT))
sys.path.insert(0, str(HERE))

os.environ.setdefault("JARVIS_ENABLED", "true")
os.environ.setdefault("JARVIS_MODE", "SHADOW")
os.environ.setdefault("EXTERNAL_ACTIONS", "false")
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis import capabilities as caps  # noqa: E402
from jarvis.action_contract import ContractCache, ContractError  # noqa: E402
from jarvis.execution_planner import plan_request  # noqa: E402
from jarvis.context import ContextCompiler  # noqa: E402
from jarvis.memory import CompanyMemory, MemoryError as JarvisMemoryError  # noqa: E402
from jarvis.operator import OperatorSession  # noqa: E402
from jarvis.phase2 import Phase2Runtime  # noqa: E402
from jarvis.shadow import ShadowRunner  # noqa: E402
from jarvis.transport import memory_host  # noqa: E402

import auth  # noqa: E402
import chat  # noqa: E402

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
STATIC_DIR = HERE / "static"
BIND_HOST = os.environ.get("JARVIS_WEB_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("JARVIS_WEB_PORT", "8091"))

SESSION_COOKIE = "jarvis_session"
CSRF_COOKIE = "jarvis_csrf"

sessions = auth.SessionStore()
throttle = auth.LoginThrottle()

_memory = CompanyMemory(host=memory_host())
_shadow_runner = ShadowRunner(Phase2Runtime(ContextCompiler(_memory)))
_operator = OperatorSession(host=memory_host())


def _live_registry() -> dict:
    """The capability registry the planner is checked against.

    Built from the same live evidence ContextCompiler already uses -- one
    Company Memory probe plus the loaded action contract. A failed probe or an
    unloadable contract yields absent evidence, which build_registry turns into
    UNKNOWN/MISSING rather than an optimistic guess, so the planner then blocks
    the affected step instead of planning around a capability nobody verified.
    """
    try:
        probe_evidence = _memory.get_capability_state()
        probe = probe_evidence.records[0] if probe_evidence.records else {}
    except JarvisMemoryError:
        probe = {}
    health = probe.get("health")
    memory_ok = isinstance(health, dict) and "checked_at" in health
    try:
        contract = ContractCache(_memory).get()
    except (ContractError, JarvisMemoryError):
        contract = None
    return caps.build_registry(probe=probe, contract=contract, memory_ok=memory_ok)


def _client_ip(handler: "Handler") -> str:
    # Trusted only because Caddy sets it (header_up SET, matches the existing
    # X-Gercek-IP convention this project already relies on elsewhere).
    forwarded = handler.headers.get("X-Gercek-IP")
    return forwarded or handler.client_address[0]


def _read_json_body(handler: "Handler") -> dict:
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if length <= 0 or length > 65536:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _parse_cookies(handler: "Handler") -> dict[str, str]:
    raw = handler.headers.get("Cookie", "")
    out = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            out[key] = value
    return out


def _tail_jsonl(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "JarvisWebConsole/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter, no client details leaked
        sys.stderr.write("[web] " + (fmt % args) + "\n")

    # -- response helpers ---------------------------------------------------
    def _send_json(self, status: int, payload: dict, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or []):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if path.suffix in (".html",):
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(data)

    def _set_session_cookies(self, session: auth.Session) -> list[tuple[str, str]]:
        secure = "; Secure" if os.environ.get("JARVIS_WEB_INSECURE_COOKIES") != "1" else ""
        return [
            ("Set-Cookie", f"{SESSION_COOKIE}={session.session_id}; Path=/; HttpOnly{secure}; SameSite=Strict"),
            ("Set-Cookie", f"{CSRF_COOKIE}={session.csrf_token}; Path=/{secure}; SameSite=Strict"),
        ]

    def _clear_session_cookies(self) -> list[tuple[str, str]]:
        return [
            ("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; Max-Age=0; SameSite=Strict"),
            ("Set-Cookie", f"{CSRF_COOKIE}=; Path=/; Max-Age=0; SameSite=Strict"),
        ]

    def _current_session(self) -> auth.Session | None:
        cookies = _parse_cookies(self)
        sid = cookies.get(SESSION_COOKIE)
        if not sid:
            return None
        return sessions.get(sid)

    def _require_csrf(self, session: auth.Session) -> bool:
        provided = self.headers.get("X-CSRF-Token", "")
        return bool(provided) and provided == session.csrf_token

    # -- routing --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/"):
                self._route_api_get(path, parse_qs(parsed.query))
            else:
                self._route_static(path)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_json(500, {"error": "internal error"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            self._route_api_post(parsed.path)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_json(500, {"error": "internal error"})

    # -- static frontend --------------------------------------------------
    def _route_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR not in target.parents and target != STATIC_DIR:
            self._send_json(404, {"error": "not found"})
            return
        if not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = {
            ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
            ".webmanifest": "application/manifest+json",
        }.get(target.suffix, "application/octet-stream")
        self._send_file(target, content_type)

    # -- authenticated API --------------------------------------------------
    def _route_api_get(self, path: str, query: dict) -> None:
        if path == "/api/login":
            self._send_json(405, {"error": "use POST"})
            return

        session = self._current_session()
        if path == "/api/session":
            if session is None:
                self._send_json(200, {"authenticated": False})
                return
            self._send_json(200, {"authenticated": True, "username": session.username,
                                  "csrf_token": session.csrf_token})
            return

        if session is None:
            self._send_json(401, {"error": "authentication required"})
            return

        if path == "/api/status":
            self._send_json(200, self._build_status())
            return
        if path == "/api/activity":
            limit = int((query.get("limit") or ["30"])[0])
            limit = max(1, min(limit, 200))
            audit = _tail_jsonl(STATE_DIR / "audit.jsonl", limit)
            findings = _tail_jsonl(STATE_DIR / "findings.jsonl", limit)
            self._send_json(200, {"audit": audit, "findings": findings})
            return
        if path == "/api/panel":
            # Bolum listesi: uc nokta kesfedilebilir olsun, arayuz sabit
            # isim listesi tasimak zorunda kalmasin.
            self._send_json(200, {"sections": ["veri", "ajanlar", "raporlar", "ayarlar"]})
            return
        if path.startswith("/api/panel/"):
            section = path.rsplit("/", 1)[-1]
            builder = {"veri": _panel_veri, "ajanlar": _panel_ajanlar,
                       "raporlar": _panel_raporlar, "ayarlar": _panel_ayarlar}.get(section)
            if builder is None:
                self._send_json(404, {"error": "unknown panel"})
                return
            self._send_json(200, builder())
            return
        if path == "/api/proposals":
            try:
                pending = _operator.list_pending()
                self._send_json(200, {"pending": pending})
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
            return
        if path.startswith("/api/proposals/"):
            action_id = path.rsplit("/", 1)[-1]
            try:
                proposal = _operator.inspect(int(action_id))
            except (ValueError, TypeError):
                self._send_json(400, {"error": "invalid action id"})
                return
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            if proposal is None:
                self._send_json(404, {"error": "not found (pending only)"})
                return
            self._send_json(200, proposal)
            return

        self._send_json(404, {"error": "not found"})

    def _route_api_post(self, path: str) -> None:
        if path == "/api/login":
            self._handle_login()
            return

        session = self._current_session()
        if session is None:
            self._send_json(401, {"error": "authentication required"})
            return
        if not self._require_csrf(session):
            self._send_json(403, {"error": "csrf token missing or invalid"})
            return

        if path == "/api/logout":
            sessions.destroy(session.session_id)
            self._send_json(200, {"ok": True}, self._clear_session_cookies())
            return
        if path == "/api/chat":
            body = _read_json_body(self)
            message = str(body.get("message", ""))[:2000]
            try:
                result = chat.route(message, _shadow_runner, _operator)
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            self._send_json(200, result)
            return
        if path == "/api/chat/stream":
            self._handle_chat_stream()
            return
        if path == "/api/plan":
            # REQUEST -> PLAN -> DISPLAY. This endpoint plans and returns;
            # it never executes a step. jarvis.execution_planner touches no
            # database, spawns no subprocess and calls no model, so the only
            # I/O here is the read-only registry probe above.
            body = _read_json_body(self)
            message = str(body.get("message", ""))[:2000]
            try:
                plan = plan_request(message, registry=_live_registry())
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            self._send_json(200, plan.to_dict())
            return
        if path.startswith("/api/proposals/") and path.endswith("/decide"):
            action_id = path.split("/")[-2]
            body = _read_json_body(self)
            decision = str(body.get("decision", ""))
            reason = str(body.get("reason", ""))[:2000]
            try:
                result = _operator.decide(int(action_id), decision, reason)
                self._send_json(200, result)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
            return

        self._send_json(404, {"error": "not found"})

    def _handle_chat_stream(self) -> None:
        """Streams {"type":"stage"|"done", ...} frames as newline-delimited
        JSON (one object per line) over a single-use, Connection: close
        response. Chosen over EventSource because EventSource cannot send a
        POST body; a fetch() + ReadableStream reader on the frontend
        consumes this the same way it would consume real SSE, and the frame
        shape is what a future token-streaming model router extends (see
        chat.stream's docstring) -- so switching later needs no protocol
        change, only more frame types.
        """
        body = _read_json_body(self)
        message = str(body.get("message", ""))[:2000]
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for event in chat.stream(message, _shadow_runner, _operator):
                line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
        except (JarvisMemoryError, BrokenPipeError, ConnectionResetError) as exc:
            try:
                line = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
            except OSError:
                pass
        self.close_connection = True

    def _handle_login(self) -> None:
        source = _client_ip(self)
        allowed, retry_after = throttle.check(source)
        if not allowed:
            self._send_json(429, {"error": "too many attempts", "retry_after_s": retry_after})
            return
        body = _read_json_body(self)
        username = str(body.get("username", ""))
        password = str(body.get("password", ""))
        account = auth.load_account()
        ok = False
        if account and username == account["username"]:
            ok = auth.verify_password(password, account["password_hash"], account["salt"])
        if not ok:
            throttle.record_failure(source)
            self._send_json(401, {"error": "invalid credentials"})
            return
        throttle.record_success(source)
        session = sessions.create(username)
        self._send_json(200, {"ok": True, "username": username, "csrf_token": session.csrf_token},
                        self._set_session_cookies(session))

    # -- status -----------------------------------------------------------
    def _build_status(self) -> dict:
        started = time.time()
        health = None
        health_error = None
        try:
            evidence = _memory.get_system_status()
            health = evidence.records[0] if evidence.records else {}
        except Exception as exc:  # noqa: BLE001
            health_error = str(exc)

        contract_valid = None
        try:
            contract_valid = ContractCache(_memory).get().valid
        except Exception:  # noqa: BLE001
            contract_valid = None

        pending_count = None
        try:
            pending_count = len(_operator.list_pending())
        except Exception:  # noqa: BLE001
            pending_count = None

        audit = _tail_jsonl(STATE_DIR / "audit.jsonl", 1)
        last_cycle = audit[0] if audit else None
        recent_proposed = bool(last_cycle and last_cycle.get("result") == "PROPOSED"
                               and time.time() - started < 60)

        if health_error:
            visual_state = "OFFLINE"
        elif pending_count:
            visual_state = "WAITING_APPROVAL"
        elif recent_proposed:
            visual_state = "PROPOSING"
        else:
            visual_state = "IDLE"

        return {
            "visual_state": visual_state,
            "company_memory": {"healthy": health_error is None, "error": health_error, "health": health},
            "action_firewall": {"contract_valid": contract_valid},
            "pending_proposals": pending_count,
            "last_cycle": last_cycle,
            "external_actions_enabled": os.environ.get("EXTERNAL_ACTIONS_ANNOUNCED", "false") == "true",
            "server_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }


def main() -> None:
    account = auth.ensure_operator_account()
    if account:
        username, password = account
        sys.stderr.write(
            f"\n[jarvis-web] Operator account created.\n  username: {username}\n  password: {password}\n"
            "  (shown once -- store it now; only the hash is kept)\n\n"
        )
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    sys.stderr.write(f"[jarvis-web] listening on {BIND_HOST}:{BIND_PORT}\n")
    server.serve_forever()


# ==========================================================================
# Panel bolumleri
# ==========================================================================
# Dort bolum de OLCULEN durumu gosterir. Okunamayan bir kaynak "yok" diye
# gizlenmez, hatasiyla birlikte gosterilir: panelin iki yonde de yalan
# soylememesi CR-001'in bulgusuydu.

def _panel_error(exc: Exception) -> dict:
    return {"status": "ERROR", "error": str(exc)[:300]}


def _panel_veri() -> dict:
    """Company Memory'nin gercek durumu: hangi sorgu calisiyor, kac satir."""
    # Modul zaten bir CompanyMemory ornegi tutuyor; ikincisini kurmak
    # transport ayarini ikiye bolerdi.
    memory = _memory
    domains = []
    for domain, names in getattr(type(memory), "DOMAIN_QUERIES", {}).items():
        queries = []
        for name in names:
            try:
                evidence = memory._fetch(name)
                queries.append({"name": name, "status": "OK",
                                "rows": len(evidence.records),
                                "latency_ms": evidence.latency_ms,
                                "source": evidence.source})
            except Exception as exc:  # noqa: BLE001
                queries.append({"name": name, "status": "FAIL",
                                "error": str(exc)[:160]})
        domains.append({"domain": domain, "queries": queries,
                        "ok": sum(1 for q in queries if q["status"] == "OK"),
                        "total": len(queries)})

    provenance, quality = [], []
    try:
        for row in memory.get_provenance().records:
            provenance.append({"alan": row.get("entity_id"),
                               "authority": row.get("authority"),
                               "freshness": row.get("freshness"),
                               "connection": row.get("current_connection"),
                               "observed_at": row.get("observed_at")})
    except Exception as exc:  # noqa: BLE001
        provenance = [_panel_error(exc)]
    try:
        for row in memory.get_data_quality().records:
            quality.append({"check": row.get("entity_id"),
                            "passed": row.get("passed"),
                            "detail": str(row.get("detail") or "")[:200]})
    except Exception as exc:  # noqa: BLE001
        quality = [_panel_error(exc)]

    return {"domains": domains, "provenance": provenance, "quality": quality}


def _role_reality() -> dict:
    """Rollerin gerçekte ne olduğu ve son koşuda ne ürettikleri.

    Panelin 28 satiri, 28 farkli yetenek DEGILDIR. Bunu yazmamak, sistemi
    oldugundan buyuk gostermek olur.
    """
    out: dict = {
        "note": ("8 ajans rolü kod tarafında yalnız etikettir; aralarında "
                 "davranış farkı yoktur. 20 uzmanın hepsi tek sınıftır "
                 "(DeterministicSpecialist) ve yalnız hangi veriyi "
                 "istedikleriyle ayrışır. Aşağıdaki tablo son ajans "
                 "koşusunda her rolün gerçekten ne ürettiğini gösterir."),
        "last_run": None, "contributions": [],
    }
    try:
        from jarvis import agency_store
        son = agency_store.recent(1)
        if not son:
            return out
        kayit = agency_store.get(son[0]["id"]) or {}
        teslimat = kayit.get("deliverable") or {}
        out["last_run"] = {"task": teslimat.get("task"),
                           "product": teslimat.get("product"),
                           "objective": teslimat.get("objective")}
        out["contributions"] = teslimat.get("role_contributions") or []
    except Exception as exc:  # noqa: BLE001 - panel hicbir zaman cokmez
        out["error"] = str(exc)[:200]
    return out


def _team_opinions() -> list:
    """Ekip üyeleri ve bu veriye bakınca söyledikleri. Sıfır model çağrısı."""
    try:
        from jarvis.roster import opinions
        return opinions(_memory)
    except Exception as exc:  # noqa: BLE001 - panel hicbir zaman cokmez
        return [_panel_error(exc)]


def _panel_ajanlar() -> dict:
    """Roller, saglayicilar ve motor adaylari -- hangisi gercekten kullanilabilir."""
    roles, providers, engines = [], [], []
    reality = _role_reality()
    try:
        from jarvis import agency
        for role in agency.ROLES:
            roles.append({"id": role, "kind": "agency"})
    except Exception as exc:  # noqa: BLE001
        roles.append(_panel_error(exc))
    try:
        from jarvis.specialist_pool import SPECIALISTS
        for spec in SPECIALISTS:
            roles.append({"id": getattr(spec, "specialist_id", str(spec)),
                          "kind": "specialist",
                          "domain": getattr(spec, "domain", None)})
    except Exception:  # noqa: BLE001
        pass
    try:
        from webconsole.conversation import _router
        states = _router().provider_states()
        providers = [{"provider": k, "state": v} for k, v in states.items()] \
            if isinstance(states, dict) else [{"provider": str(states), "state": "?"}]
    except Exception as exc:  # noqa: BLE001
        providers = [_panel_error(exc)]
    try:
        from jarvis.adapter_factory import AdapterFactory
        for candidate in AdapterFactory.candidates():
            engines.append({"name": candidate.name, "version": candidate.version,
                            "state": candidate.state.value,
                            "evidence": candidate.evidence})
    except Exception as exc:  # noqa: BLE001
        engines = [_panel_error(exc)]
    return {"team": _team_opinions(), "role_reality": reality, "roles": roles, "providers": providers, "engines": engines}


def _panel_raporlar() -> dict:
    """Bulgular ve dongu ozeti -- uretilmis gercek kayitlar."""
    findings = _tail_jsonl(STATE_DIR / "findings.jsonl", 60)
    audit = _tail_jsonl(STATE_DIR / "audit.jsonl", 60)

    by_code: dict = {}
    for row in findings:
        key = row.get("signal_code") or row.get("signature") or "infra"
        entry = by_code.setdefault(key, {"code": key, "count": 0,
                                         "severity": row.get("severity"),
                                         "last": None, "reason": row.get("reason")})
        entry["count"] += 1
        entry["last"] = row.get("observed_at") or entry["last"]

    cycles = [r for r in audit if r.get("cycle")]
    results: dict = {}
    for row in cycles:
        results[row.get("result", "?")] = results.get(row.get("result", "?"), 0) + 1
    last = cycles[-1] if cycles else {}

    # Gecmis kararlarin sonucundan cikan dersler. Okunamazsa uydurulmaz:
    # learning.run zaten status=UNAVAILABLE dondurur ve panel onu gosterir.
    try:
        from jarvis import learning
        lessons = learning.run(_memory)
    except Exception as exc:  # noqa: BLE001
        lessons = {"status": "ERROR", "error": str(exc)[:200]}

    return {
        "lessons": lessons,
        "findings": sorted(by_code.values(), key=lambda e: -e["count"]),
        "finding_total": len(findings),
        "cycle_results": [{"result": k, "count": v} for k, v in
                          sorted(results.items(), key=lambda kv: -kv[1])],
        "last_cycle": {"cycle": last.get("cycle"), "result": last.get("result"),
                       "business": last.get("business"),
                       "model_calls": last.get("model_calls"),
                       "external_actions": last.get("external_actions"),
                       "total_ms": last.get("total_ms")},
    }


def _panel_ayarlar() -> dict:
    """Yonetisim anahtarlari -- SALT OKUNUR.

    Panelden degistirilemez: EXTERNAL_ACTIONS ve kill switch sahibin kararidir
    ve tarayicidan degistirilebilir olmasi Action Firewall'un anlamini bozar.
    """
    env = {}
    try:
        for line in pathlib.Path("/etc/lcarlie/jarvis-phase2.env").read_text(
                encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                if any(s in key.upper() for s in ("TOKEN", "KEY", "SECRET", "PASS")):
                    continue  # sir degeri panele tasinmaz
                env[key.strip()] = value.strip()
    except Exception as exc:  # noqa: BLE001
        env = {"error": str(exc)[:200]}

    thresholds = {}
    try:
        from jarvis.business_signals import DEFAULT_THRESHOLDS
        thresholds = dict(DEFAULT_THRESHOLDS)
    except Exception:  # noqa: BLE001
        pass

    compliance = {}
    try:
        from jarvis.compliance import PUBLISHED_TEXT_ACTIONS, RULES_SOURCE
        compliance = {"rules_source": RULES_SOURCE,
                      "gated_actions": sorted(PUBLISHED_TEXT_ACTIONS)}
    except Exception:  # noqa: BLE001
        pass

    return {
        "env": env, "thresholds": thresholds, "compliance": compliance,
        "readonly": True,
        "note": ("Bu degerler panelden degistirilemez. EXTERNAL_ACTIONS ve kill "
                 "switch sunucuda, sahibin karariyla degisir."),
        "kill_switch": ("systemctl stop jarvis-phase2.timer && "
                        "systemctl disable jarvis-phase2.timer"),
    }


if __name__ == "__main__":
    main()
