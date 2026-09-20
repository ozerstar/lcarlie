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
import threading
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
from jarvis import conversation_memory as _cmem  # noqa: E402
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


# ==========================================================================
# Host kaynak olcumu (CPU / RAM / DISK)
# ==========================================================================
# Panel bugune kadar bu ucu icin "N/A" yaziyordu ve notu "uc nokta yok"
# diyordu -- dogruydu: capabilities.host_resources() yalnizca TOPLAM RAM ve
# cekirdek SAYISINI veriyor, kullanimi degil, ve API'ye hic cikmiyordu.
# Burasi o bosluk. Uc deger de cekirdegin kendi sayaclarindan okunur:
#
#   CPU   /proc/stat       iki olcum ARASINDAKI fark. "Anlik CPU yuzdesi"
#                          diye bir sey yoktur; yuzde ancak bir zaman araligi
#                          icin tanimlidir, o yuzden aralik da raporlanir.
#   RAM   /proc/meminfo    MemTotal - MemAvailable. MemFree DEGIL: sayfa
#                          onbellegi geri alinabilir, onu "dolu" saymak
#                          sunucuyu oldugundan dolu gosterirdi.
#   DISK  os.statvfs("/")  kok dosya sistemi; yuzde df ile ayni yontemle,
#                          yani root'a ayrilan yedek haric hesaplanir.
#
# Okunamayan alan None doner ve panelde N/A kalir, sebebiyle birlikte.
# Tahmin, varsayilan veya "yaklasik" bir sayi hicbir yolda uretilmez.

_CPU_LOCK = threading.Lock()
_CPU_PREV: "tuple[float, float, float] | None" = None   # (zaman, toplam, bos)


def _read_cpu_sample() -> "tuple[float, float] | None":
    """/proc/stat'in toplu `cpu` satirindan (toplam, bos) jiffy."""
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            line = handle.readline()
    except OSError:
        return None
    parts = line.split()
    if len(parts) < 6 or parts[0] != "cpu":
        return None
    try:
        values = [float(x) for x in parts[1:11]]
    except ValueError:
        return None
    # user nice system idle iowait irq softirq steal guest guest_nice
    return sum(values), values[3] + values[4]


def _cpu_percent() -> dict:
    """Iki olcum arasindaki farktan CPU kullanimi.

    Panel 12 saniyede bir /api/status cagirdigi icin normal durumda pencere o
    iki istek arasidir -- istegi hic bekletmez. Karsilastirilacak taze bir
    onceki ornek yoksa (ilk istek, ya da uzun aradan sonra) burada kendi
    200 ms'lik penceresini alir: kisa ama GERCEK bir olcum, "veri yok"
    demekten iyi ve uydurma degil.
    """
    global _CPU_PREV
    first = _read_cpu_sample()
    if first is None:
        return {"percent": None, "error": "/proc/stat okunamadi"}
    now = time.time()
    with _CPU_LOCK:
        prev = _CPU_PREV
        _CPU_PREV = (now, first[0], first[1])

    if prev is not None and 1.0 <= (now - prev[0]) <= 300.0:
        window = now - prev[0]
        total_delta = first[0] - prev[1]
        idle_delta = first[1] - prev[2]
    else:
        time.sleep(0.2)
        second = _read_cpu_sample()
        if second is None:
            return {"percent": None, "error": "/proc/stat okunamadi"}
        window = 0.2
        total_delta = second[0] - first[0]
        idle_delta = second[1] - first[1]
        with _CPU_LOCK:
            _CPU_PREV = (time.time(), second[0], second[1])

    if total_delta <= 0:
        return {"percent": None, "error": "olcum araligi bos"}
    busy = max(0.0, total_delta - idle_delta)
    return {"percent": round(min(100.0, busy / total_delta * 100.0), 1),
            "window_s": round(window, 1)}


def _ram_usage() -> dict:
    fields: dict[str, float] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    fields[key] = float(rest.split()[0])   # kB
                    if len(fields) == 2:
                        break
    except (OSError, ValueError, IndexError):
        return {"percent": None, "error": "/proc/meminfo okunamadi"}
    total = fields.get("MemTotal") or 0.0
    available = fields.get("MemAvailable")
    if total <= 0 or available is None:
        return {"percent": None, "error": "MemTotal/MemAvailable yok"}
    used = total - available
    kib_per_gib = 1024.0 * 1024.0
    return {"percent": round(used / total * 100.0, 1),
            "used_gib": round(used / kib_per_gib, 2),
            "total_gib": round(total / kib_per_gib, 2)}


def _disk_usage(mount: str = "/") -> dict:
    try:
        st = os.statvfs(mount)
    except OSError:
        return {"percent": None, "error": f"{mount} okunamadi"}
    block = st.f_frsize or st.f_bsize
    total = st.f_blocks * block
    free_user = st.f_bavail * block        # root yedegi HARIC
    used = total - st.f_bfree * block
    denom = used + free_user
    if total <= 0 or denom <= 0:
        return {"percent": None, "error": "bos dosya sistemi"}
    gib = 1024.0 ** 3
    return {"percent": round(used / denom * 100.0, 1),
            "used_gib": round(used / gib, 2),
            "total_gib": round(total / gib, 2),
            "mount": mount}


def _host_metrics() -> dict:
    cpu = _cpu_percent()
    cpu["cores"] = os.cpu_count()
    try:
        cpu["load"] = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        cpu["load"] = None
    return {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "cpu": cpu, "ram": _ram_usage(), "disk": _disk_usage("/")}


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
        if path == "/api/kreatif":
            try:
                evidence = _memory._fetch("kreatif_performans")
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "kreatif verisi okunamadi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, {
                "rows": evidence.records,
                "source": evidence.source,
                "latency_ms": evidence.latency_ms,
                # Panelin esigi kendi uydurmamasi icin sunucudan gelir.
                "ornek_esigi": 1000,
            })
            return
        if path == "/api/urun-alanlari":
            try:
                evidence = _memory._fetch("urun_alan_karsilastirma")
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "urun alanlari okunamadi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, {
                "rows": evidence.records,
                "source": evidence.source,
                "latency_ms": evidence.latency_ms,
                # Panel bu satiri gostermeli: duzenleme dogrudan uygulanmaz.
                "uyari": ("Degisiklikler dogrudan uygulanmaz; onay kuyruguna "
                          "gonderilir. Dis platforma yazma izni kapali."),
            })
            return
        if path == "/api/fiyat-matrisi":
            try:
                evidence = _memory._fetch("platform_fiyat_matrisi")
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "fiyat matrisi okunamadi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, {
                "rows": evidence.records,
                "source": evidence.source,
                "latency_ms": evidence.latency_ms,
                # Panelin "bu sayi ne kadar guvenilir" diyebilmesi icin.
                "uyari": ("Maliyet sahip beyanidir (tum urunlere ortalama "
                          "400 TL), gercek urun maliyeti degildir. Marj "
                          "yaklasiktir."),
            })
            return
        if path == "/api/hafiza":
            self._send_json(200, _hafiza_gorunumu())
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
        if path == "/api/fiyat-toplu-onizleme":
            # ONIZLEME: hicbir sey yazilmaz, yalniz hesaplanir.
            body = _read_json_body(self)
            if not isinstance(body, dict):
                self._send_json(400, {"error": "gecersiz govde"})
                return
            try:
                sonuc = _toplu_onizleme(body)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "onizleme uretilemedi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, sonuc)
            return
        if path == "/api/hafiza":
            # Not EKLEME. Hicbir sey cikarim yapmaz: buraya yalnizca
            # operatorun kendi yazdigi cumle girer. Hafizanin neyi
            # saklayacagina kendi karar vermesi, duzeltilemeyen bir
            # hafizadir -- jarvis.conversation_memory.remember()'in
            # varlik sebebi de bu.
            body = _read_json_body(self)
            note = str(body.get("note", ""))[:400]
            if not note.strip():
                self._send_json(400, {"error": "bos not kaydedilmez"})
                return
            eklendi = _cmem.remember(note, source="panel")
            if not eklendi:
                self._send_json(503, {"error": "not yazilamadi"})
                return
            payload = _hafiza_gorunumu()
            payload["eklendi"] = True
            self._send_json(200, payload)
            return
        if path == "/api/hafiza/sil":
            # SILME parcaya gore calisir (conversation_memory.forget).
            # Kac notun gittigini DONDURUYORUZ: metin baska bir notun
            # icinde de geciyorsa iki not birden gider ve operator bunu
            # sonradan degil, o anda gormeli.
            body = _read_json_body(self)
            fragment = str(body.get("fragment", ""))[:400]
            if not fragment.strip():
                self._send_json(400, {"error": "bos parca ile silinmez"})
                return
            silinen = _cmem.forget(fragment)
            payload = _hafiza_gorunumu()
            payload["silinen"] = silinen
            self._send_json(200, payload)
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
            # Olculmus host kullanimi. Panelin CPU/RAM/DISK alanlari yalnizca
            # bunu basar; okunamayan alan None gelir ve N/A kalir.
            "host": _host_metrics(),
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


# ---------------------------------------------------------------------
# HAFIZA
#
# Kisisel asistan katmani (jarvis.conversation_memory + jarvis.hatira)
# 20.09.2026'da kuruldu ve calisiyordu, ama panelde HICBIR yuzu yoktu:
# ne bir ekran, ne bir uc nokta. Gorunmeyen bir hafiza denetlenemez --
# operator neyin hatirlandigini goremiyorsa, yanlis hatirlanan bir seyi
# de duzeltemez. Bu uclar o boslugu kapatir.
#
# Iki kaynak bilerek AYRI raporlanir:
#   dosya  -- notun aslI (state/conversation/<thread>.notes.jsonl)
#   dizin  -- mem0/pgvector, yalnizca ARAMA katmani
# Ayni sayiyi tek etiketle gostermek, dizin coktugunde paneli yalanci
# yapardI. Ikisi ayrildigi icin panel "dizin geride kalmis" diyebiliyor.
# ---------------------------------------------------------------------

HAFIZA_UYARI = ("Notun aslı dosyada tutulur; dizin yalnızca aramayı "
                "hızlandırır. Dizin çökerse not kaybolmaz, arama körelir.")


def _hafiza_dizin_durumu() -> dict:
    """Arama dizininin OLCULEN durumu. Ithal bile tembel: mem0 agir bir
    bagimlilik ve panel acilmadan yuklenmesi icin sebep yok."""
    try:
        from jarvis import hatira
        return hatira.durum()
    except Exception as exc:  # noqa: BLE001
        # Dizin yoksa hafiza calismaya devam eder; bu bir arIza degil,
        # bildirilecek bir durum. Panel farki gorsun diye "kurulu: false".
        return {"kurulu": False, "telemetri_kapali": None,
                "hata": f"{type(exc).__name__}: {str(exc)[:200]}",
                "not_sayisi": None}


def _hafiza_gorunumu() -> dict:
    notlar = _cmem.note_rows()
    dizin = _hafiza_dizin_durumu()
    dosya = _cmem.status()
    tutarli = (dizin.get("not_sayisi") == len(notlar)) if dizin.get("kurulu") else None
    return {
        "notlar": notlar,
        "dosya": dosya,
        "dizin": dizin,
        "tutarli": tutarli,
        "sinir": _cmem.MAX_NOTES,
        "uyari": HAFIZA_UYARI,
    }


def _yeni_fiyat(mevcut: float, yontem: str, deger: float) -> float:
    """Toplu islemin urettigi yeni fiyat. Yuvarlama KURUSTA, asagi degil:
    899.99 gibi bir sayiyi 899.99 birakmak panelde okunmaz hale getirirdi."""
    if yontem == "YUZDE":
        return round(mevcut * (1 + deger / 100.0), 2)
    if yontem == "SABIT_EKLE":
        return round(mevcut + deger, 2)
    if yontem == "SABIT_FIYAT":
        return round(deger, 2)
    raise ValueError(f"bilinmeyen yontem: {yontem}")


def _marj_hesapla(fiyat: float, komisyon: float | None, kdv: float,
                  maliyet: float | None) -> dict:
    """Gorunumdeki formulun AYNISI. Iki yerde iki farkli hesap olmamali.

    Eksik girdi uydurulmaz: komisyon veya maliyet yoksa marj None doner ve
    uyari neyin eksik oldugunu soyler.
    """
    if komisyon is None:
        return {"marj": None, "marj_yuzde": None, "uyari": "KOMISYON_YOK"}
    if maliyet is None:
        return {"marj": None, "marj_yuzde": None, "uyari": "MALIYET_YOK"}
    net = (fiyat * (1 - komisyon / 100.0)) / (1 + kdv / 100.0)
    marj = net - maliyet
    yuzde = (100.0 * marj / net) if net else None
    if marj < 0:
        uyari = "ZARAR"
    elif yuzde is not None and yuzde < 10:
        uyari = "KRITIK"
    elif yuzde is not None and yuzde < 25:
        uyari = "DUSUK"
    else:
        uyari = "OK"
    return {"marj": round(marj, 2),
            "marj_yuzde": round(yuzde, 1) if yuzde is not None else None,
            "uyari": uyari}


def _toplu_onizleme(body: dict) -> dict:
    """Toplu fiyat islemini HESAPLAR, uygulamaz.

    Amac tek: onaya gitmeden once "bu islem kac urunu zarara sokuyor"
    sorusunu cevaplamak.
    """
    platform = str(body.get("platform") or "").strip()
    yontem = str(body.get("yontem") or "").strip().upper()
    if not platform:
        raise ValueError("platform zorunlu")
    try:
        deger = float(body.get("deger"))
    except (TypeError, ValueError):
        raise ValueError("deger sayi olmali") from None
    secili = body.get("urun_idler") or []

    rows = [r for r in _memory._fetch("platform_fiyat_matrisi").records
            if r.get("platform_kod") == platform]
    if secili:
        secili = set(secili)
        rows = [r for r in rows if r.get("urun_id") in secili]
    if not rows:
        raise ValueError("eslesen urun yok")

    satirlar, sayac = [], {"ZARAR": 0, "KRITIK": 0, "DUSUK": 0, "OK": 0,
                           "KOMISYON_YOK": 0, "MALIYET_YOK": 0, "FIYAT_YOK": 0}
    for r in rows:
        mevcut = r.get("gecerli_fiyat")
        if mevcut is None:
            sayac["FIYAT_YOK"] += 1
            satirlar.append({"urun_id": r.get("urun_id"),
                             "urun_adi": r.get("urun_adi"),
                             "eski_fiyat": None, "yeni_fiyat": None,
                             "uyari": "FIYAT_YOK"})
            continue
        yeni = _yeni_fiyat(float(mevcut), yontem, deger)
        if yeni <= 0:
            raise ValueError("islem sifir veya negatif fiyat uretiyor")
        komisyon = r.get("komisyon_yuzde")
        maliyet = r.get("birim_maliyet")
        marj = _marj_hesapla(
            yeni,
            float(komisyon) if komisyon is not None else None,
            float(r.get("kdv_yuzde") or 20),
            float(maliyet) if maliyet is not None else None)
        sayac[marj["uyari"]] = sayac.get(marj["uyari"], 0) + 1
        satirlar.append({
            "urun_id": r.get("urun_id"), "urun_adi": r.get("urun_adi"),
            "eski_fiyat": float(mevcut), "yeni_fiyat": yeni,
            "marj": marj["marj"], "marj_yuzde": marj["marj_yuzde"],
            "uyari": marj["uyari"],
        })

    return {
        "platform": platform, "yontem": yontem, "deger": deger,
        "urun_sayisi": len(satirlar), "ozet": sayac, "satirlar": satirlar,
        "uygulandi": False,
        "not": ("Bu bir ONIZLEMEDIR; hicbir fiyat degistirilmedi. "
                "Uygulanmasi icin onay kuyruguna gonderilmelidir."),
    }

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


def _panel_usage() -> dict:
    """Son 7 günün model kullanımı. Para tahmin edilmez, token sayılır."""
    try:
        from jarvis.usage import summary
        return summary(days=7)
    except Exception as exc:  # noqa: BLE001 - panel hicbir zaman cokmez
        return {"error": str(exc)[:200], "providers": [], "total_calls": 0,
                "paid_calls": 0}


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

    return {"model_usage": _panel_usage(), 
        "env": env, "thresholds": thresholds, "compliance": compliance,
        "readonly": True,
        "note": ("Bu degerler panelden degistirilemez. EXTERNAL_ACTIONS ve kill "
                 "switch sunucuda, sahibin karariyla degisir."),
        "kill_switch": ("systemctl stop jarvis-phase2.timer && "
                        "systemctl disable jarvis-phase2.timer"),
    }


if __name__ == "__main__":
    main()
