"""Review-pending deliveries must not appear as completed on the dashboard."""
import datetime
import unittest
from unittest.mock import patch

import ekip_isleri


class ReviewSummaryTest(unittest.TestCase):
    def test_only_accepted_deliveries_count_as_completed(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for quality in ("GECTI", "KISMI"):
            with self.subTest(quality=quality):
                pending = {"durum": "INCELEME_BEKLIYOR", "teslim": {
                    "kalite": quality, "yonetici": "INCELEME_BEKLIYOR", "tarih": now}}
                accepted = {"durum": "TESLIM_EDILDI", "teslim": {
                    "kalite": quality, "yonetici": "ONAY", "tarih": now}}
                tree = {"departmanlar": {"SEO": {"gorevler": [pending, accepted]}}}
                with patch.object(ekip_isleri, "_agac", return_value=tree):
                    summary = ekip_isleri.ozet()
                    self.assertEqual(summary["teslim_bugun"], 1)
                    self.assertEqual(summary["kismi_bugun"], int(quality == "KISMI"))
                    self.assertEqual(len(ekip_isleri.teslimler()["kayitlar"]), 1)
                    self.assertEqual(ekip_isleri.acik_isler()["ozet"]["INCELEME_BEKLIYOR"], 1)
