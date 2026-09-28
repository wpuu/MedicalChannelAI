from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS = [
    ROOT / "ops" / "edgeone-cn-proxy" / "edge-functions" / "index.js",
    ROOT / "ops" / "edgeone-cn-proxy" / "edge-functions" / "[[default]].js",
]


class EdgeOneProxyContractTest(unittest.TestCase):
    def test_edgeone_handlers_use_supported_shape(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertIn("export default async function onRequest(context)", text)
            self.assertIn("context.request", text)
            self.assertNotIn('from "../proxy.js"', text)
            self.assertNotIn("addEventListener", text)

    def test_preview_token_is_not_forwarded_to_origin(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertIn('key !== "eo_token"', text)
            self.assertIn('key !== "eo_time"', text)

    def test_runtime_errors_are_visible(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertIn("MCAI Edge proxy runtime error:", text)
            self.assertIn('"x-mcai-edge-proxy": "runtime-error"', text)


if __name__ == "__main__":
    unittest.main()
