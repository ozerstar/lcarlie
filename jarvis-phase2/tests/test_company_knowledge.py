"""Company knowledge: retrieval, Turkish folding and the internal boundary."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.company_knowledge import (  # noqa: E402
    CompanyKnowledge, fold)

KNOWLEDGE = Path(os.environ.get(
    "JARVIS_KNOWLEDGE_DIR",
    str(Path(__file__).resolve().parents[1] / "knowledge")))


class FoldTest(unittest.TestCase):
    def test_dotted_capital_does_not_grow_a_combining_mark(self):
        # "İ".casefold() is "i" + COMBINING DOT ABOVE, which matches nothing.
        self.assertEqual(fold("İDDİA"), "iddia")
        self.assertEqual(fold("FİYAT"), "fiyat")

    def test_dotless_and_dotted_i_collapse_together(self):
        # Both sides fold the same way, so the distinction can be dropped --
        # and it must be, because the brand names are typed in ASCII.
        self.assertEqual(fold("SATIŞ"), fold("satış"))
        self.assertEqual(fold("Intimblanc"), fold("İNTİMBLANC"))
        self.assertEqual(fold("Intimblanc"), "intimblanc")


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.k = CompanyKnowledge(KNOWLEDGE)

    def test_knowledge_is_installed(self):
        self.assertTrue(self.k.available, f"no documents in {KNOWLEDGE}")

    def test_identity_is_short_enough_to_load_every_turn(self):
        identity = self.k.identity()
        self.assertIn("L'CARLIÉ", identity)
        self.assertLess(len(identity), 1500)

    def test_front_matter_is_parsed(self):
        doc = self.k.documents["21-fiyat"]
        self.assertIn("fiyat", doc.keywords)
        self.assertIn("kupon", doc.keywords)
        self.assertFalse(doc.internal)

    def test_multiline_keyword_list_is_parsed(self):
        doc = self.k.documents["30-urun-vireon"]
        self.assertIn("tribulus", doc.keywords)   # second line of the list
        self.assertIn("damiana", doc.keywords)    # last item
        self.assertTrue(doc.internal)

    def test_missing_directory_is_not_an_error(self):
        empty = CompanyKnowledge(KNOWLEDGE / "yok")
        self.assertFalse(empty.available)
        self.assertEqual(empty.identity(), "")
        self.assertEqual(empty.context("vireon fiyatı"), "")


class RetrieveTest(unittest.TestCase):
    def setUp(self):
        self.k = CompanyKnowledge(KNOWLEDGE)

    def _names(self, query, **kw):
        return [d.name for d in self.k.retrieve(query, **kw)]

    def test_every_document_fits_the_budget(self):
        # The failure this closes is invisible: a file larger than the budget
        # is skipped silently and the model answers with no knowledge at all.
        # A topic that outgrows one file is SPLIT, never allowed to exceed it.
        from jarvis.company_knowledge import _MAX_CHARS
        oversized = {name: len(doc.body)
                     for name, doc in self.k.documents.items()
                     if len(doc.body) > _MAX_CHARS}
        self.assertEqual({}, oversized,
                         f"larger than the {_MAX_CHARS}-char budget, so they "
                         "would never be retrieved: split them")

    def test_price_question_retrieves_the_price_correction(self):
        # "Vireon kaç para?" matches both the price file and the product file,
        # and only one fits the budget. Either is acceptable ONLY if it carries
        # the correction -- the known failure is quoting 2.400, the struck-out
        # reference price, as the amount due.
        block = self.k.context("Vireon kaç para?")
        self.assertIn("1.200", block)
        self.assertIn("2.400", block)

    def test_a_pure_price_question_retrieves_the_price_file(self):
        # Where the coupon trap and the 146-question measurement live.
        self.assertIn("21-fiyat", self._names("Kupon kodu ve indirim durumu ne?"))

    def test_product_question_retrieves_the_product(self):
        self.assertIn("30-urun-intimblanc", self._names("Intimblanc nedir?"))

    def test_claim_question_retrieves_the_rules(self):
        self.assertIn("10-iddia-kurallari",
                      self._names("Bu cümleyi yazabilir miyim, mevzuat uygun mu?"))

    def test_rewording_question_retrieves_the_substitution_table(self):
        # Split out of the claim rules so the most-retrieved file stays small.
        self.assertIn("12-karsilik-tablosu",
                      self._names("Bunun yerine ne yazayım?"))

    def test_number_question_retrieves_measurement_truths(self):
        self.assertIn("50-olcum-gercekleri",
                      self._names("Ciro ve marj rakamları ölçümde güvenilir mi?"))

    def test_a_revenue_question_gets_the_traps_not_the_price_list(self):
        # A number question must arrive with the caveats attached -- KDV, the
        # 18.8% inflated revenue, the estimated cost. The price file used to
        # win this on the generic keyword "ne kadar", which was removed from
        # it for exactly that reason; "kaç para" still carries price intent.
        self.assertEqual(["50-olcum-gercekleri"],
                         self._names("Bu ay ciro ne kadar?"))

    def test_identity_is_never_retrieved(self):
        # It is loaded unconditionally; retrieving it too would double it.
        self.assertNotIn("00-kimlik", self._names("L'CARLIÉ kimdir?"))

    def test_index_is_not_retrieved(self):
        self.assertNotIn("INDEX", self._names("index dizin bilgi"))

    def test_unrelated_question_retrieves_nothing(self):
        self.assertEqual(self._names("bugün hava nasıl olacak"), [])

    def test_budget_is_respected(self):
        from jarvis.company_knowledge import _MAX_CHARS, _MAX_DOCS
        docs = self.k.retrieve("vireon fiyat iddia ürün ciro")
        self.assertLessEqual(len(docs), _MAX_DOCS)
        self.assertLessEqual(sum(len(d.body) for d in docs), _MAX_CHARS)

    def test_subject_beats_a_passing_mention(self):
        # The 36-product list mentions every product; the product's own file
        # is about it. The specific file must win.
        ranked = self.k.score("Intimblanc hakkında ne biliyorsun?")
        self.assertEqual(ranked[0][1].name, "30-urun-intimblanc")


class InternalBoundaryTest(unittest.TestCase):
    """The old catalog may inform Jarvis; it may never reach a customer.

    DESIGN DECISION -- the warnings quote the forbidden phrasing verbatim.

    Every product file ends its compliant half with a "⚠️ Metin yazarken"
    warning that names the banned sentence in full, e.g. *"kolajen sentezini
    destekler" yazılamaz*. That means a forbidden string is present in a
    copy context, and a test that greps for the string alone flags the
    prohibition as if it were the violation.

    The warnings stay, for two reasons. A rule that names the exact phrase is
    the only form that reliably stops a model reproducing it -- "avoid
    structural claims" does not. And the claim-rules file already works this
    way: its whole job is to list forbidden terms, so banning their presence
    would ban the rules themselves.

    The boundary that is actually enforced is therefore the source, not the
    vocabulary: **no line from a document's internal section may appear in a
    copy context.** That is what these tests assert, computed from the corpus
    rather than from a hand-written list, so it cannot drift as files are
    added.
    """

    #: Below this length a line is punctuation, a heading or a stock phrase,
    #: not a quoted claim worth matching on.
    SUBSTANTIAL = 40

    def setUp(self):
        self.k = CompanyKnowledge(KNOWLEDGE)

    def _internal_lines(self, doc):
        """The lines that exist only in this document's internal half."""
        full = doc.text(internal_ok=True)
        public = doc.text(internal_ok=False)
        public_lines = {line.strip().lower() for line in public.splitlines()}
        lines = []
        for line in full.splitlines():
            line = line.strip().lower().lstrip("> ")
            if len(line) >= self.SUBSTANTIAL and line not in public_lines:
                lines.append(line)
        return lines

    def test_every_internal_document_actually_has_internal_lines(self):
        # Guards the guard: if this returned nothing the leak test would pass
        # vacuously.
        for doc in self.k.documents.values():
            if doc.internal:
                self.assertTrue(self._internal_lines(doc),
                                f"{doc.name} is marked ic-bilgi but has no "
                                "internal lines to protect")

    def test_internal_section_is_present_when_allowed(self):
        body = self.k.documents["30-urun-vireon"].text(internal_ok=True)
        self.assertIn("İÇ BİLGİ", body)
        self.assertIn("ereksiyon süresinin", body)

    def test_internal_section_is_removed_for_copy(self):
        doc = self.k.documents["30-urun-vireon"]
        body = doc.text(internal_ok=False)
        self.assertNotIn("İÇ BİLGİ", body)
        self.assertNotIn("ereksiyon süresinin", body.lower())
        # What remains is still useful: the compliant framing survives, and so
        # does the warning that names "ereksiyon" as unwritable.
        self.assertIn("INCI", body)
        self.assertIn("hiçbiri yazılamaz", body)

    def test_wholly_internal_document_is_withheld_entirely(self):
        doc = self.k.documents["40-eski-katalog-ic-bilgi"]
        self.assertTrue(doc.internal)
        self.assertEqual(doc.text(internal_ok=False), "")

    def test_no_internal_line_reaches_a_copy_context(self):
        protected = {doc.name: self._internal_lines(doc)
                     for doc in self.k.documents.values() if doc.internal}
        # The exact shape the Agency uses.
        for query in ("vireon reklam metni", "femisia caption",
                      "dermavasc ürün açıklaması", "liftelle caption",
                      "intimblanc reklam metni", "eski katalog",
                      "vireon femisia intimblanc liftelle dermavasc katalog"):
            lowered = self.k.context(query, internal_ok=False).lower()
            self.assertNotIn("iç bilgi —", lowered,
                             f"internal heading leaked for query {query!r}")
            for name, lines in protected.items():
                for line in lines:
                    self.assertNotIn(line, lowered,
                                     f"{name}: internal line leaked for "
                                     f"query {query!r}: {line[:60]!r}")

    def test_the_prohibition_itself_survives_for_copy(self):
        # The counterpart of the rule above: what is stripped is the catalog's
        # claim, never the warning that the claim may not be written.
        for name in ("30-urun-vireon", "30-urun-liftelle", "30-urun-femisia",
                     "30-urun-dermavasc", "30-urun-intimblanc"):
            body = self.k.documents[name].text(internal_ok=False)
            self.assertIn("Metin yazarken", body, name)
            self.assertIn("yazılamaz", body, name)


class AgencyPromptTest(unittest.TestCase):
    """The boundary where it actually matters: the Agency writes copy.

    Asserting on ``context(internal_ok=False)`` proves the function behaves;
    this proves the caller passes the right flag, which is the part that can
    silently regress.
    """

    def setUp(self):
        self.k = CompanyKnowledge(KNOWLEDGE)

    def _agency_system(self, task):
        # Rebuilt exactly as AgencyCapability._synthesize does.
        return "\n\n".join(
            part for part in (self.k.identity(),
                              self.k.context(task, internal_ok=False))
            if part)

    def test_agency_prompt_carries_no_internal_line(self):
        boundary = InternalBoundaryTest("test_no_internal_line_reaches_a_copy_context")
        boundary.setUp()
        protected = [line
                     for doc in self.k.documents.values() if doc.internal
                     for line in boundary._internal_lines(doc)]
        self.assertTrue(protected)
        for task in ("Vireon için reklam metni yaz",
                     "Liftelle kampanya konsepti",
                     "Femisia sosyal medya içeriği",
                     "Dermavasc landing page metni"):
            system = self._agency_system(task).lower()
            for line in protected:
                self.assertNotIn(line, system,
                                 f"internal line leaked into agency prompt "
                                 f"for {task!r}: {line[:60]!r}")

    def test_agency_still_gets_the_identity_and_the_rules(self):
        system = self._agency_system("Vireon için reklam metni yaz")
        self.assertIn("L'CARLIÉ", system)
        self.assertIn("yazılamaz", system)

    def test_agency_call_site_passes_internal_ok_false(self):
        # A guard against the flag being dropped in a future edit.
        source = (Path(__file__).resolve().parents[1]
                  / "jarvis" / "agency.py").read_text(encoding="utf-8")
        self.assertIn("internal_ok=False", source)


class ContextTest(unittest.TestCase):
    def setUp(self):
        self.k = CompanyKnowledge(KNOWLEDGE)

    def test_context_is_labelled_and_grounded(self):
        block = self.k.context("vireon fiyatı ne kadar")
        self.assertTrue(block.startswith("ŞİRKET BİLGİSİ"))
        self.assertIn("1.200", block)

    def test_context_is_empty_on_a_miss(self):
        self.assertEqual(self.k.context("merhaba nasılsın"), "")


if __name__ == "__main__":
    unittest.main()
