"""Guards the redesigned console's contract with the backend and the CSP.

The UI redesign changed only static/ -- no route, no payload, no security
middleware. These tests exist so that stays true: they fail if the frontend
starts calling an endpoint the server does not serve, if it needs a CSP
relaxation to render, or if it begins displaying numbers the backend never
measured.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
APP_PY = Path(__file__).resolve().parent.parent / "app.py"

INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
APP_CSS = (STATIC / "app.css").read_text(encoding="utf-8")
SERVER = APP_PY.read_text(encoding="utf-8")

# Every path the frontend may call, and the reason each one is legitimate.
KNOWN_ROUTES = {
    "/api/session", "/api/login", "/api/logout", "/api/status",
    "/api/activity", "/api/proposals", "/api/chat", "/api/chat/stream",
    "/api/plan", "/api/panel",
}

# Arka ucu olan bolumler. Bu kume, navigasyonun neyi sunabilecegini belirler:
# bir sekme ancak buraya girdikten sonra etkinlestirilebilir.
BACKED_VIEWS = {"home", "analiz", "gorevler", "veri", "ajanlar", "raporlar", "ayarlar"}
PANEL_VIEWS = {"veri", "ajanlar", "raporlar", "ayarlar"}


class FrontendCallsOnlyRealEndpoints(unittest.TestCase):
    def _called_paths(self) -> set[str]:
        paths = set()
        for match in re.finditer(r"""(?:api|fetch)\(\s*[`'"]([^`'"]+)[`'"]""", APP_JS):
            paths.add(match.group(1))
        # template literals like `/api/proposals/${id}/decide`
        for match in re.finditer(r"""fetch\(\s*`([^`]+)`""", APP_JS):
            paths.add(match.group(1))
        for match in re.finditer(r"""api\(\s*`([^`]+)`""", APP_JS):
            paths.add(match.group(1))
        return paths

    def test_every_called_path_is_served(self):
        for raw in self._called_paths():
            path = raw.split("?")[0]
            # normalise the two dynamic forms the proposal API uses
            path = re.sub(r"\$\{[^}]+\}", "<id>", path)
            base = path
            if base.startswith("/api/proposals/"):
                base = "/api/proposals"
            base = base.rstrip("/") or "/"
            if base.startswith("/api/proposals") and path != "/api/proposals":
                # /api/proposals/<id> and /api/proposals/<id>/decide are both
                # routed by prefix in app.py; assert those handlers exist.
                self.assertIn('path.startswith("/api/proposals/")', SERVER)
                continue
            self.assertIn(base, KNOWN_ROUTES, f"frontend calls unserved path {raw!r}")

    def test_known_routes_all_exist_in_the_server(self):
        for route in KNOWN_ROUTES:
            self.assertIn(f'"{route}"', SERVER, f"{route} is not routed in app.py")

    def test_plan_endpoint_is_display_only(self):
        # The plan view must never grow an "execute" affordance: execution is
        # gated behind the human-approval path, not a button in the browser.
        self.assertIn("openPlan", APP_JS)
        self.assertNotIn("executePlan", APP_JS)


class StaysInsideTheContentSecurityPolicy(unittest.TestCase):
    """CSP served by Caddy: script-src 'self'; style-src 'self' (no unsafe-inline)."""

    def test_no_inline_script_block(self):
        self.assertIsNone(re.search(r"<script(?![^>]*\ssrc=)[^>]*>", INDEX),
                          "inline <script> would need script-src 'unsafe-inline'")

    def test_no_inline_style_block_or_attribute(self):
        self.assertNotIn("<style", INDEX.lower())
        self.assertIsNone(re.search(r"\sstyle\s*=\s*[\"']", INDEX),
                          "style= attribute would need style-src 'unsafe-inline'")
        self.assertIsNone(re.search(r"setAttribute\(\s*['\"]style['\"]", APP_JS),
                          "setAttribute('style', ...) would need style-src 'unsafe-inline'")

    def test_no_inline_event_handlers(self):
        self.assertIsNone(re.search(r"\son(click|load|error|submit|change)\s*=", INDEX))

    def test_no_remote_asset(self):
        """Nothing may load off-origin: connect-src/style-src/script-src are 'self'.

        Comments are stripped first -- the ban is on actual references, not on
        a comment that explains why there are none.
        """
        def strip_comments(text: str) -> str:
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            text = re.sub(r"(?m)^\s*//.*$", "", text)
            return re.sub(r"(?s)<!--.*?-->", "", text)

        for raw, label in ((INDEX, "index.html"), (APP_CSS, "app.css"), (APP_JS, "app.js")):
            text = strip_comments(raw)
            self.assertIsNone(re.search(r"""(?:src|href|url\()\s*=?\s*["'(]?\s*(?:https?:)?//""", text),
                              f"{label} loads an off-origin asset")
            self.assertNotIn("@import", text, f"{label} uses @import")


class ShowsNoNumberTheBackendNeverMeasured(unittest.TestCase):
    def test_cpu_ram_disk_render_as_not_available(self):
        # /api/status carries no host utilisation, so these must stay N/A.
        for metric in ("mCpu", "mRam", "mDisk"):
            self.assertRegex(INDEX, rf'id="{metric}"[^>]*>N/A<')

    def test_no_synthetic_values_in_the_frontend(self):
        self.assertNotIn("Math.random", APP_JS)

    def test_audit_rows_are_labelled_by_cycle_not_a_fabricated_time(self):
        # audit.jsonl records `cycle`, never a timestamp; findings carry a real
        # observed_at. The feed must not invent a clock for the former.
        self.assertIn("DÖNGÜ #", APP_JS)
        self.assertIn("observed_at", APP_JS)


class ExecutionSurfaceStaysHonest(unittest.TestCase):
    """The execution UI is prepared, not simulated.

    The runtime is not reachable over HTTP yet. These tests fail if the
    frontend starts inventing a route to it, or starts showing progress the
    backend never reported.
    """

    def test_no_invented_execution_endpoint(self):
        for invented in ("/api/execute", "/api/run", "/api/runs", "/api/execution"):
            self.assertNotIn(invented, APP_JS,
                             f"frontend invents {invented}; app.py serves no such route")

    def test_run_data_is_read_only_from_an_explicit_guard(self):
        # A run is rendered only when the backend actually attaches one in the
        # shape execution_runtime.RunRecord.to_dict() already produces.
        self.assertIn("function extractRun(", APP_JS)
        self.assertIn("state.lastRun = extractRun(body)", APP_JS)

    def test_no_progress_percentage_anywhere(self):
        """The backend reports a per-step status, never a ratio.

        Checked against code with comments removed -- a comment explaining why
        there is no percentage is not a percentage.
        """
        code = re.sub(r"/\*.*?\*/", "", APP_JS, flags=re.S)
        code = re.sub(r"(?m)^\s*//.*$", "", code)
        for pattern in (r"['\"`]\s*%\s*['\"`]", r"\+\s*['\"]%['\"]", r"toFixed\(",
                        r"\bpercent\b", r"progress-bar", r"width\s*:\s*\$\{"):
            self.assertIsNone(re.search(pattern, code),
                              f"{pattern} implies a fabricated progress value")
        markup = re.sub(r"(?s)<!--.*?-->", "", INDEX)
        self.assertNotIn("progress", markup.lower())

    def test_stage_and_domain_states_use_the_backend_vocabulary(self):
        # Mapped straight off execution_runtime.py's own step statuses.
        for status in ("PENDING", "SUCCEEDED", "FAILED", "DATA_UNAVAILABLE",
                       "BLOCKED_CAPABILITY", "BLOCKED_UPSTREAM",
                       "REQUIRES_HUMAN_ORIGINATION", "PROPOSED"):
            self.assertIn(status, APP_JS, f"{status} is not mapped to a UI state")

    def test_absent_evidence_says_so(self):
        self.assertIn("Kanıt bulunamadı", APP_JS)

    def test_proposed_panel_never_claims_an_action_was_applied(self):
        self.assertIn("ÖNERİ — uygulanmadı", APP_JS)
        self.assertIn("Bu panel hiçbir aksiyonu uygulamaz", INDEX)
        for claim in ("uygulandı", "deploy edildi", "reklam değiştirildi", "yayınlandı"):
            self.assertNotIn(claim, APP_JS, f"UI claims {claim!r} without backend confirmation")

    def test_external_evidence_links_are_scheme_checked(self):
        self.assertIn("function safeUrl(", APP_JS)
        self.assertIn("parsed.protocol === 'http:'", APP_JS)

    def test_skeleton_stages_do_not_animate(self):
        # Only a stage the backend reports as RUNNING may pulse.
        self.assertIn(".exec-stage.st-run .exec-stage-state { animation:", APP_CSS)
        self.assertIsNone(re.search(r"\.exec-stage\.st-(absent|ready|wait)[^{]*\{[^}]*animation:", APP_CSS),
                          "a stage with no run data animates")


class NavigationOnlyOffersBackedViews(unittest.TestCase):
    """Kural degismedi: arka ucu olmayan sekme etkinlestirilemez.

    Degisen, hangi bolumlerin arka ucu oldugu. VERI/AJANLAR/RAPORLAR/AYARLAR
    artik /api/panel/<bolum> uzerinden gercek olcum donduruyor, bu yuzden
    BACKED_VIEWS kumesine girdiler. Kume disinda kalan her yeni sekme
    disabled kalmak zorunda -- bu testin asil isi bu.
    """

    def test_unbacked_sections_stay_disabled(self):
        for match in re.finditer(r'<button[^>]*data-view="([a-z]+)"[^>]*>', INDEX):
            view = match.group(1)
            if view in BACKED_VIEWS:
                continue
            self.assertIn("disabled", match.group(0),
                          f"{view} has no backend but is enabled")

    def test_backed_sections_are_enabled(self):
        for view in sorted(BACKED_VIEWS):
            match = re.search(rf'<button[^>]*data-view="{view}"[^>]*>', INDEX)
            self.assertIsNotNone(match, f"{view} nav item missing")
            self.assertNotIn("disabled", match.group(0))

    def test_every_panel_view_has_a_container_and_renderer(self):
        """Etkin bir sekme, govdesi ve cizicisi olmadan acilamaz."""
        for view in sorted(PANEL_VIEWS):
            self.assertIn(f'id="view{view.capitalize()}"', INDEX, f"{view} view eksik")
            self.assertIn(f'id="{view}Body"', INDEX, f"{view} govdesi eksik")
            self.assertIn(f"render{view.capitalize()}", APP_JS, f"{view} cizicisi eksik")

    def test_panel_sections_are_registered_in_the_view_map(self):
        for view in sorted(PANEL_VIEWS):
            self.assertRegex(APP_JS, rf"{view}:\s*'view{view.capitalize()}'",
                             f"{view} VIEWS haritasinda yok")

    def test_quick_actions_map_onto_real_capabilities(self):
        # Each quick action is either a refresh of existing GETs or a chat turn.
        asks = re.findall(r'class="qa-btn" data-ask="([^"]+)"', INDEX)
        self.assertTrue(asks, "quick actions lost their chat bindings")
        self.assertIn("qaRefresh", INDEX)


class PreservesTheExistingOperatorControls(unittest.TestCase):
    def test_command_bar_keeps_plan_and_send(self):
        for element_id in ("chatForm", "chatInput", "planBtn", "sendBtn", "stopBtn", "retryBtn"):
            self.assertIn(f'id="{element_id}"', INDEX, f"{element_id} disappeared from the command bar")

    def test_enter_still_submits(self):
        # the input lives in a <form> whose submit handler sends the message
        self.assertIn("chatForm').addEventListener('submit'", APP_JS)

    def test_approval_controls_survive(self):
        for needle in ("btnApprove", "btnReject", "decisionReason", "/decide"):
            self.assertIn(needle, APP_JS)

    def test_motion_is_compositor_friendly_and_respects_reduced_motion(self):
        self.assertIn("prefers-reduced-motion", APP_CSS)
        # only transform/opacity are animated
        for block in re.findall(r"@keyframes\s+[\w-]+\s*\{(.*?)\n\}", APP_CSS, re.S):
            props = re.findall(r"^\s*([a-z-]+)\s*:", block, re.M)
            self.assertTrue(set(props) <= {"transform", "opacity"},
                            f"non-compositor property animated: {sorted(set(props))}")


if __name__ == "__main__":
    unittest.main()

class ModuleRunsAsMainTests(unittest.TestCase):
    """app.py __main__ olarak calisirken de butun isleyicileri tanimali.

    Yasanan hata: panel fonksiyonlari dosyanin SONUNA, yani
    `if __name__ == "__main__": main()` satirindan SONRA eklenmisti.
    main() icindeki serve_forever() blokladigi icin o tanimlara hic
    ulasilmiyordu; servis calisiyor ama her istek NameError veriyordu.

    Testler bunu gormemisti cunku modulu IMPORT ediyorlar -- import sirasinda
    dosyanin tamami calisir ve tanimlar olusur. Fark yalnizca __main__
    yolunda ortaya cikiyor, o yuzden bu test satir sirasini olcer.
    """

    @property
    def _source(self) -> str:
        return APP_PY.read_text(encoding="utf-8")

    def _line_of(self, prefix: str) -> int:
        for index, line in enumerate(self._source.split("\n"), 1):
            if line.startswith(prefix):
                return index
        return -1

    def test_every_handler_is_defined_before_the_main_guard(self):
        guard = self._line_of('if __name__ == "__main__"')
        self.assertGreater(guard, 0, "__main__ korumasi bulunamadi")
        for name in ("_panel_veri", "_panel_ajanlar", "_panel_raporlar",
                     "_panel_ayarlar", "_panel_error", "_tail_jsonl", "def main"):
            prefix = name if name.startswith("def ") else f"def {name}"
            line = self._line_of(prefix)
            self.assertGreater(line, 0, f"{name} tanimli degil")
            self.assertLess(line, guard,
                            f"{name} __main__ korumasindan SONRA tanimli -- "
                            "servis calisirken NameError verir")

    def test_main_guard_is_the_last_statement(self):
        """Korumadan sonra calisabilir kod kalmamali."""
        after = self._source.split('if __name__ == "__main__":', 1)[1]
        kalan = [line for line in after.split("\n")[1:]
                 if line.strip() and not line.startswith((" ", "\t", "#"))]
        self.assertEqual(kalan, [], f"korumadan sonra kod var: {kalan[:3]}")


class PanelCallsGoThroughApiTests(unittest.TestCase):
    """Panel istekleri api() uzerinden gitmeli, ham fetch ile degil.

    api() 401'i yakalayip giris ekranina donuyor. Ham fetch ile yazildiginda
    servis yeniden baslatilip oturumlar dusunce panel "Bolum yuklenemedi"
    diyordu: kullanici hatanin bolumde oldugunu saniyor, oysa yalnizca
    yeniden giris yapmasi gerekiyor. Bir kez yasandi.
    """

    def test_load_section_uses_api_helper(self):
        source = APP_JS[APP_JS.index("async function loadSection"):]
        source = source[:source.index("\n}")]
        self.assertIn("await api(", source)
        self.assertNotIn("fetch(", source)

    def test_load_section_names_the_lapsed_session(self):
        source = APP_JS[APP_JS.index("async function loadSection"):]
        source = source[:source.index("\n}")]
        self.assertIn("401", source)
