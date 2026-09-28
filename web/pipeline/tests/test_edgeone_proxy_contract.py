from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
MIDDLEWARE = ROOT / "ops" / "edgeone-cn-proxy" / "middleware.js"
EDGE_FUNCTIONS = ROOT / "ops" / "edgeone-cn-proxy" / "edge-functions"


class EdgeOneProxyContractTest(unittest.TestCase):
    def test_middleware_uses_official_rewrite_contract(self):
        text = MIDDLEWARE.read_text(encoding="utf-8")
        self.assertIn("export function middleware(context)", text)
        self.assertIn("const { request, rewrite } = context", text)
        self.assertIn("return rewrite(targetUrl.toString())", text)
        self.assertIn('matcher: "/:path*"', text)

    def test_root_maps_to_today_without_browser_redirect(self):
        text = MIDDLEWARE.read_text(encoding="utf-8")
        self.assertIn('incomingUrl.pathname === "/" ? "/today" : incomingUrl.pathname', text)
        self.assertNotIn("redirect(", text)

    def test_preview_token_is_not_forwarded(self):
        text = MIDDLEWARE.read_text(encoding="utf-8")
        self.assertIn('key !== "eo_token"', text)
        self.assertIn('key !== "eo_time"', text)

    def test_failing_edge_function_proxy_is_removed(self):
        self.assertFalse(EDGE_FUNCTIONS.exists())
        self.assertFalse((ROOT / "ops" / "edgeone-cn-proxy" / "proxy.js").exists())


if __name__ == "__main__":
    unittest.main()
