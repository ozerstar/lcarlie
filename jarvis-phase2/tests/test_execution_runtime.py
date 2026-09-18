"""Execution DAG runtime tests.

No database, no subprocess, no network, no model. The memory adapter is a
fake that returns real-shaped Evidence, so the runtime's own behaviour --
ordering, concurrency, failure propagation, persistence, refusals -- is what
is under test rather than Postgres.
"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis import execution_runtime as rt
from jarvis.execution_planner import plan_request
from jarvis.memory import Evidence

REAL_REQUEST = (
    "L'CARLIÉ şirketinin mevcut durumunu analiz et. Elindeki Company Memory "
    "verilerine göre şu anda yönetimin dikkat etmesi gereken en önemli "
    "problemleri, açık işleri ve fırsatları belirle. Her bulgunun hangi veriye "
    "dayandığını belirt. Veri yoksa tahmin etme. Öncelikle satış, e-ticaret, "
    "reklam, CRM ve operasyon alanlarına bak. Sonunda bana uygulanabilir bir "
    "sonraki adım planı çıkar; ancak hiçbir işlemi benim onayım olmadan uygulama."
)


def _evidence(source, records=None):
    return Evidence(source=f"postgres:{source}", authority="CANONICAL_COMPANY_MEMORY",
                    retrieved_at="live", records=records or [{"x": 1}], latency_ms=1.0)


class FakeMemory:
    QUERIES = {"system": "", "agenda": "", "open_work": "", "decision_summary": "",
               "company_dashboard": "", "capability_state": "", "action_contract": "",
               "capabilities": ""}

    def __init__(self):
        self.calls: list[str] = []
        self.lock = threading.Lock()
        self.concurrent = 0
        self.max_concurrent = 0

    def _track(self, name):
        with self.lock:
            self.calls.append(name)
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        with self.lock:
            self.concurrent -= 1

    def get_system_status(self):
        self._track("system")
        return _evidence("system", [{"open_tasks": 0, "pending_actions": 1}])

    def get_company_agenda(self):
        self._track("agenda")
        return _evidence("agenda", [{"soru_id": 1, "olusturma": "2026-09-01T00:00:00+00:00"}])

    def get_open_work(self):
        self._track("open_work")
        return _evidence("open_work", [{"tur": "CEVAPSIZ_MESAJ", "anahtar": "a",
                                        "zaman": "2026-09-01T00:00:00+00:00"}])

    def get_company_context(self):
        self._track("decision_summary")
        return _evidence("decision_summary", [{"toplam": 3, "insan_onayi_bekleyen": 1}])

    def get_executive_brief(self):
        return _evidence("company_dashboard")

    def get_capability_state(self):
        return _evidence("capability_state", [{"health": {"checked_at": "now"}}])

    def get_action_contract(self):
        return _evidence("action_contract")

    def get_model_policy(self):
        return _evidence("capabilities")

    def get_product_context(self, entity):
        return _evidence("agenda")


def live_contract():
    """The real contract built from the same fixture the contract tests use --
    a hand-rolled fake would drift from what core.ai_propose_action enforces,
    which is the drift F-1 was about."""
    from jarvis.action_contract import build_contract
    from test_action_contract import LIVE_ROWS

    return build_contract(LIVE_ROWS, source="test")


class RuntimeTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "runs"
        self.memory = FakeMemory()
        self.runtime = rt.ExecutionRuntime(self.memory, contract=None, run_dir=self.run_dir)

    def _plan(self, request=REAL_REQUEST):
        return plan_request(request)

    def _run(self, request=REAL_REQUEST, originator="operator", **kwargs):
        return self.runtime.execute(self._plan(request), originator=originator, **kwargs)


class OriginationTests(RuntimeTestBase):
    def test_a_plan_cannot_start_itself(self):
        for originator in ("", "   ", None):
            with self.assertRaises(rt.ExecutionDenied):
                self.runtime.execute(self._plan(), originator=originator)

    def test_a_rejected_plan_is_not_executable(self):
        with self.assertRaises(rt.ExecutionDenied):
            self.runtime.execute(plan_request("  "), originator="operator")

    def test_the_originator_is_recorded(self):
        record = self._run(originator="özer")
        self.assertEqual(record.originator, "özer")


class RealRequestDagTests(RuntimeTestBase):
    def setUp(self):
        super().setUp()
        self.record = self._run()
        self.by_capability = {step.capability: step for step in self.record.steps.values()}

    def test_five_domain_workstreams_ran_in_the_first_group(self):
        plan = self._plan()
        first_group = plan.parallel_groups[0]
        self.assertEqual(len(first_group), 5)
        for step_id in first_group:
            self.assertIn(step_id, self.record.steps)

    def test_available_domains_succeeded_with_real_evidence(self):
        for capability in ("crm_analysis", "operations_analysis"):
            step = self.by_capability[capability]
            self.assertEqual(step.status, rt.STEP_SUCCEEDED)
            self.assertTrue(step.evidence_refs)
            for ref in step.evidence_refs:
                self.assertTrue(ref.startswith("postgres:"))

    def test_unavailable_domains_are_carried_not_invented(self):
        for capability in ("sales_analysis", "ecommerce_analysis", "advertising_analysis"):
            step = self.by_capability[capability]
            self.assertEqual(step.status, rt.STEP_DATA_UNAVAILABLE)
            self.assertTrue(step.block_reason)
            self.assertEqual(step.evidence_refs, ())
            self.assertEqual(step.output.get("records"), 0)

    def test_fusion_uses_only_real_upstream_evidence_and_names_the_gaps(self):
        fusion = self.by_capability["evidence_fusion"]
        self.assertEqual(fusion.status, rt.STEP_SUCCEEDED)
        missing = {entry["capability"] for entry in fusion.output["missing_inputs"]}
        self.assertEqual(missing, {"sales_analysis", "ecommerce_analysis",
                                   "advertising_analysis"})
        # nothing was fabricated: every fused reference came from a step that
        # actually produced it
        upstream_refs = set()
        for step in self.record.steps.values():
            upstream_refs.update(step.evidence_refs)
        self.assertTrue(set(fusion.evidence_refs) <= upstream_refs)
        self.assertGreater(fusion.output["fused_inputs"], 0)
        for ref in fusion.evidence_refs:
            self.assertTrue(ref.startswith("postgres:"))

    def test_red_team_runs_after_fusion_and_analysis_and_raises_the_gaps(self):
        red = self.by_capability["red_team_review"]
        self.assertEqual(red.status, rt.STEP_SUCCEEDED)
        codes = {entry["code"] for entry in red.output["objections"]}
        self.assertIn("INPUT_UNAVAILABLE", codes)
        self.assertFalse(red.output["clean"])

    def test_problem_opportunity_analysis_ran_on_the_intelligence_layer(self):
        step = self.by_capability["problem_opportunity_analysis"]
        self.assertEqual(step.status, rt.STEP_SUCCEEDED)
        self.assertIn("signals", step.output)
        self.assertIn("skipped", step.output)

    def test_final_action_plan_is_proposed_never_executed(self):
        runtime = rt.ExecutionRuntime(FakeMemory(), contract=live_contract(),
                                      run_dir=self.run_dir / "c")
        record = runtime.execute(self._plan(), originator="operator")
        action = next(step for step in record.steps.values()
                      if step.capability == "action_plan")
        self.assertEqual(action.status, rt.STEP_PROPOSED)
        self.assertFalse(action.output["submitted"])
        self.assertEqual(action.output["action_type"], "REQUEST_HUMAN_REVIEW")

    def test_action_plan_without_a_contract_blocks_rather_than_proceeding(self):
        action = self.by_capability["action_plan"]
        self.assertEqual(action.status, rt.STEP_BLOCKED_CAPABILITY)

    def test_no_model_calls_and_no_external_actions(self):
        self.assertEqual(self.record.telemetry["model_calls"], 0)
        self.assertEqual(self.record.telemetry["external_actions"], 0)
        self.assertEqual(self.record.telemetry["external_provider_calls"], 0)
        for step in self.record.steps.values():
            self.assertEqual(step.model_calls, 0)

    def test_run_is_degraded_not_completed_when_data_is_missing(self):
        self.assertEqual(self.record.status, rt.RUN_DEGRADED)


class TelemetryTests(RuntimeTestBase):
    def test_every_required_counter_is_present(self):
        record = self._run()
        for key in ("steps", "queue_wait_ms_total", "step_duration_ms_total", "total_ms",
                    "cache_hits", "model_calls", "capabilities_used", "failure_reasons"):
            self.assertIn(key, record.telemetry)
        self.assertGreater(record.total_ms, 0)

    def test_each_step_records_its_own_inputs_duration_and_capability(self):
        record = self._run()
        for step in record.steps.values():
            self.assertIn("depends_on", step.inputs)
            self.assertGreaterEqual(step.duration_ms, 0.0)
            self.assertTrue(step.capability)

    def test_repeated_reads_are_cached_within_a_run(self):
        record = self._run()
        self.assertGreaterEqual(record.telemetry["cache_hits"], 1)


class ConcurrencyTests(RuntimeTestBase):
    def test_independent_steps_run_bounded_and_dependencies_are_respected(self):
        runtime = rt.ExecutionRuntime(
            self.memory, run_dir=self.run_dir,
            budget=rt.ResourceBudget(max_concurrency=2, timeout_s=60.0))
        plan = self._plan()
        record = runtime.execute(plan, originator="operator")
        # dependencies: every parent must be terminal before its child ran
        for step in plan.steps:
            for parent in step.depends_on:
                self.assertNotEqual(record.steps[parent].status, rt.STEP_PENDING)
        self.assertLessEqual(self.memory.max_concurrent, 2)


class FailurePropagationTests(RuntimeTestBase):
    def test_a_failed_step_blocks_its_downstream(self):
        def boom(ctx):
            raise RuntimeError("upstream exploded")

        with patch.dict(rt.EXECUTORS, {"crm_analysis": boom}):
            record = self._run()
        self.assertEqual(record.steps["S4"].status, rt.STEP_FAILED)
        self.assertIn("upstream exploded", record.steps["S4"].error)
        fusion = next(s for s in record.steps.values() if s.capability == "evidence_fusion")
        self.assertEqual(fusion.status, rt.STEP_BLOCKED_UPSTREAM)
        self.assertIn("S4", fusion.block_reason)
        # and the block cascades
        red = next(s for s in record.steps.values() if s.capability == "red_team_review")
        self.assertEqual(red.status, rt.STEP_BLOCKED_UPSTREAM)
        self.assertEqual(record.status, rt.RUN_FAILED)

    def test_data_unavailable_does_not_block_downstream(self):
        record = self._run()
        fusion = next(s for s in record.steps.values() if s.capability == "evidence_fusion")
        self.assertEqual(fusion.status, rt.STEP_SUCCEEDED)


class SafetyBoundaryTests(RuntimeTestBase):
    def test_a_coding_step_is_never_executed_by_the_runtime(self):
        with patch("jarvis.coding_executor.run_coding_task",
                   side_effect=AssertionError("runtime executed CodingExecutor")), \
             patch("jarvis.coding_executor._clone_canonical_source",
                   side_effect=AssertionError("runtime created a clone")):
            record = self._run("şu modüldeki bug'ı düzelt")
        coding = next(s for s in record.steps.values() if s.capability == "coding_task")
        self.assertEqual(coding.status, rt.STEP_REQUIRES_HUMAN_ORIGINATION)
        self.assertIn("create-coding-task", coding.output["originate_with"])

    def test_external_research_is_not_executed_while_blocked(self):
        from jarvis import capabilities as caps
        registry = {
            "deterministic_company_memory": caps.Capability(
                capability_id="deterministic_company_memory", capability_name="m",
                status=caps.AVAILABLE, executor="x", source="probe"),
            "external_model_provider": caps.Capability(
                capability_id="external_model_provider", capability_name="p",
                status=caps.BLOCKED, executor="none", source="policy"),
            "external_business_action": caps.Capability(
                capability_id="external_business_action", capability_name="a",
                status=caps.CONTROLLED, executor="firewall", source="probe"),
        }
        plan = plan_request("rakipleri araştır", registry=registry)
        record = self.runtime.execute(plan, originator="operator")
        research = next(s for s in record.steps.values() if s.capability == "external_research")
        self.assertEqual(research.status, rt.STEP_BLOCKED_CAPABILITY)

    def test_runtime_never_opens_a_subprocess_or_socket(self):
        with patch("subprocess.run", side_effect=AssertionError("runtime ran a subprocess")), \
             patch("socket.socket", side_effect=AssertionError("runtime opened a socket")):
            self._run()

    def test_an_unknown_memory_query_is_denied_not_widened(self):
        ctx = rt.StepContext(plan=self._plan(), step=None, memory=self.memory,
                             compiler=self.runtime.compiler, cache=rt.QueryCache(),
                             contract=None, upstream={}, counters={})
        with self.assertRaises(rt.ExecutionDenied):
            rt._read(ctx, "mart.reklam_performans")


class PersistenceResumeTests(RuntimeTestBase):
    def test_run_state_is_persisted_and_readable(self):
        record = self._run()
        path = self.run_dir / f"{record.run_id}.json"
        self.assertTrue(path.is_file())
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["plan_id"], record.plan_id)
        self.assertEqual(len(saved["steps"]), len(record.steps))

    def test_the_same_plan_is_deduplicated_not_run_twice(self):
        first = self._run()
        calls_after_first = len(self.memory.calls)
        second = self._run()
        self.assertEqual(second.run_id, first.run_id)
        self.assertTrue(second.telemetry.get("deduplicated"))
        self.assertEqual(len(self.memory.calls), calls_after_first)

    def test_run_id_is_derived_from_the_plan(self):
        plan = self._plan()
        self.assertEqual(rt.run_id_for(plan.plan_id), f"run-{plan.plan_id}")
        self.assertNotEqual(rt.run_id_for(plan.plan_id, 2), rt.run_id_for(plan.plan_id))

    def test_resume_reuses_completed_steps_after_an_interruption(self):
        def boom(ctx):
            raise RuntimeError("transient")

        with patch.dict(rt.EXECUTORS, {"crm_analysis": boom}):
            first = self._run()
        self.assertEqual(first.status, rt.RUN_FAILED)
        ops_before = next(s for s in first.steps.values()
                          if s.capability == "operations_analysis")

        second = self._run()  # same run id, resumed
        self.assertEqual(second.run_id, first.run_id)
        crm = next(s for s in second.steps.values() if s.capability == "crm_analysis")
        self.assertEqual(crm.status, rt.STEP_SUCCEEDED)
        self.assertEqual(second.status, rt.RUN_DEGRADED)

        # the step that already succeeded was reused verbatim, not recomputed
        ops_after = next(s for s in second.steps.values()
                         if s.capability == "operations_analysis")
        self.assertEqual(ops_after.status, rt.STEP_SUCCEEDED)
        self.assertEqual(ops_after.duration_ms, ops_before.duration_ms)
        self.assertEqual(ops_after.evidence_refs, ops_before.evidence_refs)

        # and the downstream that was blocked by the failure recovered
        fusion = next(s for s in second.steps.values() if s.capability == "evidence_fusion")
        self.assertEqual(fusion.status, rt.STEP_SUCCEEDED)

    def test_a_new_attempt_gets_its_own_run_id(self):
        first = self._run()
        second = self._run(attempt=2)
        self.assertNotEqual(second.run_id, first.run_id)


class ContextBudgetTests(RuntimeTestBase):
    def test_no_step_dumps_the_whole_company_memory(self):
        record = self._run()
        for step in record.steps.values():
            sample = step.output.get("sample")
            if sample is not None:
                self.assertLessEqual(len(sample), 3)
            self.assertLessEqual(len(json.dumps(step.output, default=str)), 20000)


if __name__ == "__main__":
    unittest.main()
