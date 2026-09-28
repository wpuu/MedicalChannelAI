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

    def test_runtime_avoids_known_unsupported_constructs(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("new Headers(", text)
            self.assertNotIn("Response.json(", text)
            self.assertNotIn("process.env", text)
            self.assertNotIn("for (const [key, value] of incomingUrl.searchParams)", text)
            self.assertIn("incomingUrl.searchParams.forEach((value, key)", text)

    def test_root_maps_to_today_and_preview_token_is_filtered(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertIn('incomingUrl.pathname === "/" ? "/today" : incomingUrl.pathname', text)
            self.assertIn('key !== "eo_token"', text)
            self.assertIn('key !== "eo_time"', text)

    def test_transfer_encoding_headers_are_normalized(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertIn('lower !== "accept-encoding"', text)
            self.assertIn('requestHeaders["accept-encoding"] = "identity"', text)
            self.assertIn('lower !== "content-encoding"', text)
            self.assertIn('lower !== "transfer-encoding"', text)
            self.assertIn('lower !== "content-length"', text)

    def test_proxy_preserves_browser_origin_for_server_validation(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("requestHeaders.origin = ORIGIN", text)
            self.assertNotIn("requestHeaders.referer = ORIGIN", text)

    def test_backend_trusts_only_official_https_entry_origins(self):
        analyze = (ROOT / "web" / "api" / "ai" / "analyze.js").read_text(encoding="utf-8")
        self.assertIn("'https://medicalai.qd.je'", analyze)
        self.assertIn("'https://www.medicalai.qd.je'", analyze)
        self.assertIn("PUBLIC_FIRST_PARTY_ORIGINS.has(origin)", analyze)
        self.assertIn("host: originUrl.host", analyze)
        self.assertNotIn("'http://www.medicalai.qd.je'", analyze)

    def test_runtime_probe_exists(self):
        for path in FUNCTIONS:
            text = path.read_text(encoding="utf-8")
            self.assertIn('incomingUrl.pathname === "/__mcai_edge_probe"', text)
            self.assertIn("MCAI Edge proxy probe OK", text)

    def test_inactive_middleware_is_removed(self):
        self.assertFalse(MIDDLEWARE.exists())


if __name__ == "__main__":
    unittest.main()
