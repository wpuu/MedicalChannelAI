import json
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = WEB_ROOT / "api"
VERCEL_CONFIG = WEB_ROOT / "vercel.json"
HOBBY_FUNCTION_LIMIT = 12


def deployable_function_files():
    routes = []
    for path in API_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".js", ".py"}:
            continue
        relative = path.relative_to(API_ROOT)
        if any(part.startswith("_") for part in relative.parts):
            continue
        routes.append(relative.as_posix())
    return sorted(routes)


class VercelHobbyBudgetTests(unittest.TestCase):
    def test_serverless_function_count_keeps_one_spare_hobby_slot(self):
        routes = deployable_function_files()
        self.assertLessEqual(
            len(routes),
            HOBBY_FUNCTION_LIMIT - 1,
            f"Keep at least one spare Vercel Hobby function slot; found {len(routes)}: {routes}",
        )

    def test_private_api_routes_are_consolidated(self):
        routes = deployable_function_files()
        self.assertIn("auth.js", routes)
        self.assertIn("private.js", routes)
        for obsolete in [
            "auth/register.js",
            "auth/login.js",
            "auth/logout.js",
            "auth/me.js",
            "today.js",
            "opportunity/[id].js",
            "followup/[id].js",
            "followed.js",
            "feedback/[id].js",
        ]:
            self.assertNotIn(obsolete, routes)

    def test_discovery_continuation_reuses_existing_discover_function(self):
        routes = deployable_function_files()
        self.assertIn("ai/discover.js", routes)
        self.assertNotIn("ai/discover-continuation.js", routes)
        self.assertTrue((API_ROOT / "ai" / "_discoverContinuation.js").is_file())

    def test_main_git_push_cannot_auto_deploy_production(self):
        config = json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))
        deployment_enabled = config.get("git", {}).get("deploymentEnabled", {})
        self.assertIsInstance(deployment_enabled, dict)
        self.assertIs(
            deployment_enabled.get("main"),
            False,
            "main must remain explicitly disabled for automatic Vercel Git deployments; Production release is manual/staged only",
        )

    def test_legacy_frontend_paths_rewrite_to_consolidated_routers(self):
        config = json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))
        rewrites = {
            item.get("source"): item.get("destination")
            for item in config.get("rewrites", [])
            if isinstance(item, dict)
        }
        expected = {
            "/api/auth/register": "/api/auth?route=register",
            "/api/auth/login": "/api/auth?route=login",
            "/api/auth/logout": "/api/auth?route=logout",
            "/api/auth/me": "/api/auth?route=me",
            "/api/today": "/api/private?route=today",
            "/api/opportunity/:id": "/api/private?route=opportunity&id=:id",
            "/api/followup/:id": "/api/private?route=followup&id=:id",
            "/api/followed": "/api/private?route=followed",
            "/api/feedback/:id": "/api/private?route=feedback&id=:id",
            "/api/ai/discover-continuation": "/api/ai/discover?route=continuation",
        }
        for source, destination in expected.items():
            self.assertEqual(rewrites.get(source), destination)


if __name__ == "__main__":
    unittest.main()
