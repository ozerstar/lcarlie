import io, json, tempfile, unittest, zipfile  # noqa: F401
from pathlib import Path
from jarvis.image_jobs import ImageJobs, SLOTS

class ImageOutputSpecTest(unittest.TestCase):
    def inspect(self,spec=None):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"pack.zip"
            with zipfile.ZipFile(p,"w") as z:
                for n in range(1,40):
                    for slot in SLOTS:
                        z.writestr(f"E-TICARET/{n:02d}-urun{n}/{slot}",b"\xff\xd8jpeg\xff\xd9")
                if spec is not None:
                    z.writestr("OUTPUT-SPEC.json",json.dumps(spec))
            return ImageJobs._inspect(p)
    def test_legacy_contract_unchanged(self):
        self.assertEqual({"width":2000,"height":2000,"mode":"RGB"},self.inspect()["output_spec"])
    def test_portrait_contract_accepted(self):
        report=self.inspect({"width":3000,"height":3750,"mode":"RGB"})
        self.assertTrue(report["structural_pass"])
        self.assertEqual(195,report["image_count"])
        self.assertEqual(3750,report["output_spec"]["height"])
    def test_unsupported_contract_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect({"width":1,"height":100000,"mode":"RGB"})

if __name__=="__main__":
    unittest.main()
