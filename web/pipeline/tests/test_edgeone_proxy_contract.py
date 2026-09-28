from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS = [
    ROOT / "ops" / "edgeone-cn-proxy" / "edge-functions" / "index.js",
    ROOT / "ops" / "edgeone-cn-proxy" / "edge-functions" / "[[default]].js",
]
MIDDLEWARE = ROOT / "ops" / "edgeone-cn-proxy" / "middleware.js"


class EdgeOneProxyContractTest(unittest.TestCase):
    def test_v8_safe_edge_functions_exist(self):
        for path in FUNCTIONS:
            self.assertTrue(path.exists(), path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("export default function onRequest(context)", text)
            self.assertIn("return proxyRequest(context.request)", text)

    def test_runtime_avoids_known_unsupported_headers_constructor(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("new Headers(", text)
            self.assertNotIn("Response.json(", text)
            self.assertNotIn("process.env", text)

    def test_root_maps_to_today_and_preview_token_is_filtered(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertIn('incomingUrl.pathname === "/" ? "/today" : incomingUrl.pathname', text)
            self.assertIn('key !== "eo_token"', text)
            self.assertIn('key !== "eo_time"', text)

    def test_inactive_middleware_is_removed(self):
        self.assertFalse(MIDDLEWARE.exists())


if __name__ == "__main__":
    unittest.main()
