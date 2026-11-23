import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("component_inventory",
    Path(__file__).resolve().parents[1] / "scripts/component_inventory.py")
inventory_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory_module)


class InventoryTests(unittest.TestCase):
    def test_reads_metadata_without_executing_package_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "ruflo"
            package.mkdir()
            marker = root / "EXECUTED"
            (package / "package.json").write_text(json.dumps({
                "name": "ruflo", "version": "3.80.0",
                "exports": {"./package.json": "./evil.js"}, "token": "TOP_SECRET"}))
            (package / "evil.js").write_text(f'require("fs").writeFileSync({json.dumps(str(marker))}, "yes")')
            result = inventory_module.inventory([root], [])
            self.assertEqual(result["paketler"][0]["surum"], "3.80.0")
            self.assertFalse(marker.exists())
            self.assertNotIn("TOP_SECRET", json.dumps(result))

    def test_unknown_and_malformed_metadata_do_not_imply_safe_or_absent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ruflo").mkdir()
            (root / "ruflo/package.json").write_text('{"token":"TOP_SECRET",')
            result = inventory_module.inventory([root], [])
            self.assertEqual(result["paketler"], [])
            self.assertTrue(all(x["durum"] == "DOGRULANAMADI" for x in result["kontroller"]))
            self.assertNotIn("TOP_SECRET", json.dumps(result))

    def test_python_metadata_is_read_without_importing_distribution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dist = root / "snyk_agent_scan-0.7.0.dist-info"
            dist.mkdir()
            (dist / "METADATA").write_text('Name: snyk_agent_scan\nVersion: 0.7.0\n\n')
            result = inventory_module.inventory([], [root])
            self.assertEqual(result["paketler"][0]["paket"], "snyk-agent-scan")
            self.assertEqual(result["paketler"][0]["surum"], "0.7.0")

    def test_identity_mismatch_and_oversized_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ruflo").mkdir()
            (root / "ruflo/package.json").write_text('{"name":"unrelated","version":"1.0.0"}')
            (root / "omniroute").mkdir()
            (root / "omniroute/package.json").write_bytes(b' ' * (1024 * 1024 + 1))
            self.assertEqual(inventory_module.inventory([root], [root / "missing"])["paketler"], [])
