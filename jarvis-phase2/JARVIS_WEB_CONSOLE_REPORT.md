# SECURE JARVIS WEB CONSOLE

**OVERALL: READY_PENDING_DNS**

Everything works server-side and is verified end to end over HTTP against
the real Jarvis core. The only remaining step is external: DNS for
`jarvis.lcarlie.shop` does not exist yet (confirmed NXDOMAIN). Caddy is
configured and will auto-provision TLS the moment it resolves.

Executed 2026-09-18, 16:15–16:55 +03:00, continuing directly from the
completed Minimum Operational Jarvis state (verified, not repeated).

---

## 1. URL / ACCESS STATE

`https://jarvis.lcarlie.shop` — configured in Caddy, **waiting on DNS**.
Reachable today over plain HTTP with a `Host` header for verification
(`curl -H "Host: jarvis.lcarlie.shop" http://185.169.180.68/` → `308` redirect
to HTTPS, correct behavior), and directly on the backend port from the host
(`http://127.0.0.1:8091/`, not exposed externally — see §11).

## 2. AUTHENTICATION

Single operator account, `hashlib.scrypt` (stdlib, no bcrypt/argon2 install).
Session: signed random ID, `HttpOnly`, `Secure`, `SameSite=Strict`; 30 min
idle timeout, 12 h absolute. CSRF: double-submit token, required on every
state-changing request. Login rate limiting: 5 failures / 15 min → 15 min
lockout, per source IP. No credentials ever reach the browser in JS; the
CSRF token is the only auth-adjacent value held in a JS variable (never
`localStorage`).

First-run credential was generated randomly at first start and delivered to
the user out of band (not in this report, not in chat) — see §21.

## 3. CHAT

Real, not scripted. Two backends, both existing Jarvis code, untouched:

- `jarvis.shadow.ShadowRunner.handle()` — the exact Phase 2C/2D pipeline
  (planner → ContextCompiler → capability registry → firewall).
- `jarvis.operator.OperatorSession` — for proposal-list/inspect, which need
  the `human_approver`-only surface ShadowRunner doesn't call.

**Turkish-first, small capability boundary, not a phrase list.**
`webconsole/intents.py`: 6 capabilities, ~49 short lemmas total, plus a
Turkish-letter-safe normalizer (`İ/I/ı → i`, `bi → bir`). Verified live:
`"Vireon'u incele"`, `"vireona bak"`, `"vireon tarafında ne oluyor"` all
route to the same capability and reach the same real entity resolution in
`ContextCompiler` (which already matches "vireon" as a substring, so
Turkish suffixes attached to it needed no change at all).

**Judgement without a topic is refused truthfully:**
`"bunun için ne yapmalıyım"` → `REQUIRES_REASONING_CAPABILITY`, not a
fabricated answer. The same phrase WITH a topic (`"Vireon için ne
öneriyorsun?"`) correctly falls through to the real pipeline instead.

**Streaming**, verified live over the actual endpoint:
```
POST /api/chat/stream  (message: "Jarvis, sistem durumu ne?")
→ {"type":"stage","label":"Company Memory okunuyor"}
→ {"type":"stage","label":"Kanıtlar doğrulanıyor"}
→ {"type":"done","result":{...real data from postgres:system...}}
```
Stages are genuine steps about to run, not decorative delay — coarse-grained
because `jarvis.shadow`/`jarvis.operator` are not instrumented internally
(kept untouched, per this task's "reuse, don't duplicate" rule). No hidden
chain-of-thought is ever produced or could leak: the backend has no LLM call
in this path, so there is no reasoning trace to expose.

**Voice-ready contract:** the frontend funnels every user turn through one
function, `sendMessage(text)`; a future mic input calls the same function
with transcribed text, no other change needed. `/api/chat/stream`'s frame
shape (`stage` → `done`, future `token`) is exactly what a later
Local/Frontier Intelligence router would extend, not replace.

**Markdown-lite, tables via evidence blocks, proposal cards**: `app.js`
implements a small (~40 line) dependency-free renderer (headings, bold,
inline code, code blocks, lists) plus a dedicated proposal-card renderer for
proposal-shaped answers — chosen deliberately over a library (see §17).

## 4. COMPANY MEMORY CONNECTION

Real, verified against production: system status, VIREON entity lookup, and
pending-proposal count all returned genuine current data during testing
(§below). Zero fabricated content anywhere in the chat path.

## 5. COMMAND CENTER UI

White ivory ground, graphite type, one controlled turquoise accent,
amber/red only for semantic state — no dark theme, no neon, no generic
admin template. Layout: sticky header with live state chips (time, Jarvis,
Company Memory, Firewall, operator) → three-panel grid (intelligence feed /
abstract Jarvis presence / pending proposals) → docked chat. The presence
is inline SVG + CSS (concentric rings, a core glow/dot), not a video or
WebGL scene — five real states (`idle`/`analyzing`/`proposing`/
`waiting_approval`/`offline`) driven by `/api/status`, not fake random
motion. `prefers-reduced-motion` honored; animations pause when the tab is
hidden (`visibilitychange`).

Typography: **Monument Extended / Metropolis are not present on this host as
licensed web fonts** — a disciplined system-font fallback stack is used
instead, with the same letter-spacing/weight discipline. Recorded as a
limitation, not silently substituted with something unrelated.

## 6. DESKTOP

Three-column grid (intelligence · core · proposals), chat docked at the
bottom, full command-center feel as specified.

## 7. TABLET

Landscape: same grid, touch-sized targets. Portrait: single column,
core-first, intelligence/proposals panels below with a height cap so chat
stays reachable without excessive scrolling.

## 8. PHONE

Single column, chat-first by content order in the DOM and by panel height
caps (`max-height: 34vh` on the side panels at ≤720px), core visualization
shrinks but stays present, state chips lose their text labels and keep only
color-coded values to fit. All three breakpoints share the exact same
backend and API — no separate app.

**Honest limitation on this deliverable**: cross-device *visual* verification
(rendering in an actual mobile/tablet browser) could not be performed in
this session — there is no headless-browser tool wired to this VDS's private
network, and the public hostname has no TLS certificate yet (DNS pending).
The CSS media queries were written and reviewed for the required
breakpoints and states; a real-device pass is recommended once DNS/TLS are
live, and is a five-minute check, not new work.

## 9. PROPOSALS

`GET /api/proposals` / `GET /api/proposals/<id>` / `POST
/api/proposals/<id>/decide` — all reuse `jarvis.operator.OperatorSession`
byte-for-byte, unchanged. Verified live against production: `list`
returned real pending state (0, correctly, since none are queued right
now), and the full approve flow was exercised in the Minimum-Operational
task (proposal 20) through this exact code path.

## 10. HUMAN APPROVAL

`decide()` always runs as `human_approver`; the web process's own DB
identity is never elevated. Verified structurally (unit + integration
tests) that the ONLY operator method ever invoked by a decide request is
`decide()` — no other write path exists in `app.py`. No raw SQL anywhere in
the web layer; every DB statement lives in `jarvis.memory`/`jarvis.operator`,
already audited in Phase 2C/2D.

## 11. SECURITY

- HTTPS enforced at Caddy (HSTS, same header set as the existing
  `n8n.lcarlie.shop` block, plus a strict CSP for this app:
  `default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors
  'none'`).
- Session cookie `HttpOnly; Secure; SameSite=Strict`; CSRF cookie readable
  by JS on purpose (double-submit pattern), also `SameSite=Strict`.
- Login rate limiting verified (6th attempt in a burst → `429`).
- The web console process is **not** exposed to the internet: it binds
  `0.0.0.0:8091` on the host (needed because Caddy reaches it from inside a
  container), but `ufw` restricts port 8091 to `172.18.0.0/16` — the
  `lcarlie_web` docker bridge's own subnet — the exact same defense-in-depth
  pattern already used for n8n's port 5678 (`DENY Anywhere`). Verified: a
  request from that bridge succeeds, and the port is otherwise unreachable
  from the public interface (default-deny `ufw` policy).
- Frontend cannot reach Postgres or read any credential: verified by test
  and by construction (the only DB code paths are in `jarvis.memory`/
  `jarvis.operator`, both server-side).
- `Jarvis cannot self-approve`: structurally true — there is no code path in
  `app.py` calling anything but `OperatorSession.decide()`, and that method
  always runs as `human_approver` (Phase 2C/2D security suite re-verified
  unchanged, 32/32).

**Real incident found and fixed during this task** (disclosed in full):
applying an (ultimately reverted) `docker-compose.yml` experiment via
`docker compose up -d caddy` **recreated** the Caddy container, which
silently dropped its out-of-band `icaz_kapi` network attachment (added by
İCAZ's own `kapi-ac.sh`, which `docker compose` has no knowledge of).
`www.icaz1986.com` and `oyun.icaz1986.com` both returned `502` for a few
minutes. Found via the immediate post-change health check (not by a user
report), fixed with `docker network connect icaz_kapi lcarlie-caddy`, and
confirmed healthy again. `docker-compose.yml` was reverted and is
byte-identical (`diff` clean) to the pre-task backup. **Lesson applied and
documented**: any future Caddyfile-only change must use `docker exec
lcarlie-caddy caddy reload`, never `docker compose up` on that service —
this is exactly how the final `jarvis.lcarlie.shop` block was actually
installed, with no further container recreation.

## 12. EXTERNAL PROVIDER CALLS

**ZERO.** No LLM/model client exists anywhere in `webconsole/`; a test
(`test_no_model_calls_in_status_or_chat_path`) asserts the module source
contains no reference to any provider SDK or outbound HTTP call.

## 13. EXTERNAL ACTIONS

**ZERO.** `EXTERNAL_ACTIONS=false` unchanged in the shared env file; the web
service's own environment additionally hardcodes it, independent of that
file. Approve/reject only ever reach `core.ai_decide_action` — the same
boundary already proven fail-closed for every action type except
`REQUEST_HUMAN_REVIEW` (Minimum-Operational task), which itself only writes
an internal audit record, never an external call.

## 14. PERFORMANCE

Real measurements against production Company Memory: status endpoint ~90 ms,
proposal list ~90 ms, chat (grounded) ~100–300 ms including the two staged
events. Static assets total well under 40 KB uncompressed (no framework, no
build step, no bundler). Animations are CSS-only, paused off-tab, and
respect `prefers-reduced-motion`.

## 15. SERVICES HEALTH

All confirmed healthy after the incident and its fix:
`lcarlie-postgres`, `lcarlie-n8n`, `lcarlie-caddy`, `icaz-site`, `icaz-oyun`,
`icaz-postgres`. `jarvis-phase2.timer` active/enabled (unaffected).
`jarvis-web.service` active; kill-switch verified (`stop` → no orphan
process, connection refused → `start` → `200` again, same credential still
works).

## 16. SOURCE COMMIT

Canonical source `/opt/lcarlie/source/lcarlie-jarvis-v1`, commit
`582c2c8fba2c7ab59fb853e217c7daca959accd9`. Deployment verified
byte-identical (`rsync -ain --delete`, excluding `evidence/`/`state/`,
prints nothing). Backups taken before any mutation:
`/opt/lcarlie/backups/webconsole-20260918T162941/` (docker-compose.yml,
Caddyfile, full package, SHA-256 recorded).

## 17. OPEN-SOURCE COMPONENT EVALUATION (per this task's policy)

Researched: **assistant-ui** and **Vercel AI SDK / AI Elements**. Both are
mature, actively maintained, open-source, self-hostable TypeScript/React
toolkits (assistant-ui builds on shadcn/ui + Tailwind; the Vercel AI SDK
provides the provider-agnostic streaming/tool-calling layer they're usually
paired with). Neither requires a hosted SaaS by default and both can be
self-hosted with no token/API dependency.

**Not adopted for this task.** Reasoning:
- Both assume a React/Next.js app with an npm/Node build pipeline; this host
  runs a stdlib Python backend and a zero-build vanilla-JS frontend. Adopting
  either means introducing a full new toolchain (Node, npm install, a
  bundler) for a console that currently ships ~40 KB of static assets total.
- Their core value (token-by-token streaming render, tool-call UI,
  thread/session state management) is built for LLM responses. This backend
  currently returns **complete, deterministic answers in under a second** —
  there are no tokens to stream yet. Adopting a token-streaming UI framework
  now would mean building a nontrivial adapter to fit a non-streaming
  backend into it: complexity added for a capability not yet present,
  which this task's own instructions warn against ("do not introduce
  something to make the demo appear more sophisticated than it is").
- The specific UX asked for (staged status, streaming, Markdown, retry/stop/
  copy, proposal cards) was fully achievable natively in well under 200
  lines of reviewed, dependency-free JS, with the exact wire contract
  (`stage` → `done`, reserving `token`) that a future LLM router would want
  anyway.

Conclusion: revisit this decision if/when a real model-backed reasoning
route is connected — at that point assistant-ui or the Vercel AI SDK's
client-side stream consumer become genuinely worth the added toolchain,
and `/api/chat/stream`'s frame contract was designed so that swap needs no
change to `jarvis.shadow`/`jarvis.operator` or the rest of the backend.

Sources: [assistant-ui](https://www.assistant-ui.com/docs/integrations/frameworks/ai-sdk) ·
[Vercel AI SDK Alternatives (self-hosted, open-source options)](https://infrabase.ai/alternatives/vercel-ai-sdk) ·
[AI SDK 6 — Vercel](https://vercel.com/blog/ai-sdk-6)

## 18. OPEN BLOCKERS

**One, external: DNS.** Everything else passed.

## 19. DNS ACTION REQUIRED

Add exactly one record, matching the existing `n8n.lcarlie.shop` record:

```
Type: A
Name: jarvis.lcarlie.shop
Value: 185.169.180.68
TTL: (match existing records, e.g. 300 or provider default)
```

No other DNS change is needed. Once it propagates, Caddy retries
certificate issuance automatically (it already scheduled a retry; no
restart needed) and `https://jarvis.lcarlie.shop` becomes live with no
further action.

## 20. TESTS

57 web-console tests (auth: 16, intents: 10, chat routing: 9, full HTTP
integration: 20 — login/logout/session-expiry/CSRF/rate-limit/proposal
list-inspect-decide/self-approval-impossible/chat/streaming/path-traversal/
no-credential-leak) — **all PASS**. Full existing Jarvis suite: **108/108**,
unaffected. Security recheck re-run after all changes: **32/32 PASS**.

## 21. CREDENTIAL DELIVERY

The randomly generated first-login password was captured from the service's
own startup log (visible only to root via `journalctl -u jarvis-web`) and is
being delivered to you directly, out of band — not printed in this report or
in the chat transcript. Change it after first login by editing
`/opt/lcarlie/jarvis-phase2/state/webconsole/auth.json` via
`python3 -c "from webconsole import auth; auth.set_password('operator','<new>')"`
run from `/opt/lcarlie/jarvis-phase2` (a proper `change-password` CLI command
is a reasonable small follow-up, not implemented here to keep scope tight).

## 22. EXACT NEXT STEP

Add the DNS record in §19. Nothing else is required. Once DNS resolves,
open `https://jarvis.lcarlie.shop`, log in with the delivered credential,
and change the password.

---

JARVIS WEB CONSOLE IS OPERATIONAL (pending the one external DNS step).
JARVIS CORE REMAINS IN READ → ANALYZE → PROPOSE MODE.
EXTERNAL ACTION EXECUTION REMAINS DISABLED.
