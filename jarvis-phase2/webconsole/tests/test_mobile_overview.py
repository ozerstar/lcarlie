import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC = Path(__file__).resolve().parent.parent / "static"
MOBILE_HTML = (STATIC / "mobile" / "index.html").read_text(encoding="utf-8")
MOBILE_JS = (STATIC / "mobile" / "mobile.js").read_text(encoding="utf-8")
DESKTOP_HTML = (STATIC / "index.html").read_text(encoding="utf-8")
DESKTOP_JS = (STATIC / "app.js").read_text(encoding="utf-8")


class MobileOverviewTests(unittest.TestCase):
    def test_each_mobile_tab_has_a_panel(self):
        for tab in re.findall(r'data-tab="([^"]+)"', MOBILE_HTML):
            self.assertIn(f'id="{tab}-panel"', MOBILE_HTML)

    def test_quick_links_point_to_real_desktop_views(self):
        views = set(re.findall(r'data-view="([^"]+)"', DESKTOP_HTML))
        links = re.findall(r'href="(/\?view=[^"]+)"', MOBILE_HTML)
        self.assertGreaterEqual(len(links), 6)
        for link in links:
            self.assertIn(parse_qs(urlparse(link).query)["view"][0], views)
        self.assertIn("Object.hasOwn(VIEWS, requestedView)", DESKTOP_JS)

    def test_approvals_show_reason_and_block_empty_approval(self):
        self.assertIn("proposal.payload?.reason", MOBILE_JS)
        self.assertIn("addApprovalLine(detail, reason", MOBILE_JS)
        self.assertIn("$('approval-approve').disabled = !reason", MOBILE_JS)
        self.assertIn("approvalRisk(proposal.risk_class)", MOBILE_JS)


if __name__ == "__main__":
    unittest.main()
