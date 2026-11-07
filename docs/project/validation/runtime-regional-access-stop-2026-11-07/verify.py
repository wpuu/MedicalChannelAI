"""Verify recorded local evidence and bytes only; never execute app/SDK/tests."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(name):
    return json.loads((HERE / name).read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


s = read("validation-summary.json")
base, code = s["starting_head"], s["code_head"]
expected = {"web/collector_runtime.py", "web/pipeline/tests/test_runtime_source_parity_behavior.py"}
assert set(git("diff", "--name-only", base, code).decode().splitlines()) == expected
for path, digest in s["source_sha256"].items():
    assert sha((ROOT / path).read_bytes()) == sha(git("show", f"{code}:{path}")) == digest


def names(tree):
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


test_path = "web/pipeline/tests/test_runtime_source_parity_behavior.py"
old_tests = names(ast.parse(git("show", f"{base}:{test_path}")))
new_tests = names(ast.parse((ROOT / test_path).read_text()))
assert old_tests <= new_tests
assert sorted(new_tests - old_tests) == s["new_test_methods"]
assert len(new_tests - old_tests) == s["new_behavior_tests"] == 12

runtime_path = "web/collector_runtime.py"
before = ast.parse(git("show", f"{base}:{runtime_path}"))
after = ast.parse((ROOT / runtime_path).read_text())


def preserved_module_nodes(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
            if not isinstance(n, (ast.Import, ast.ImportFrom))
            and not (isinstance(n, ast.FunctionDef) and n.name == "_run_regional_market")]


def imports(tree):
    return {(getattr(n, "module", None), a.name, a.asname)
            for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}


assert preserved_module_nodes(before) == preserved_module_nodes(after)
assert imports(before) <= imports(after)
assert imports(after) - imports(before) == {
    ("urllib.parse", "urlsplit", None), ("sync_regional_ccgp", "RATE_LIMIT_MARKERS", None),
    ("sync_regional_ccgp", "access_block_reason", None),
}
p = read("input-integrity.json")
assert len(p["files"]) == p["protected_file_count"] == s["protected_files"] == 528
for path, digest in p["files"].items():
    assert sha((ROOT / path).read_bytes()) == digest, path
boundaries = read("unchanged-boundaries.json")
assert len(boundaries) == 453
for path, digest in boundaries.items():
    assert sha((ROOT / path).read_bytes()) == digest, path
for ref in read("source-references.json"):
    path = ROOT / ref["path"]
    assert sha(path.read_bytes()) == ref["sha256"]
    assert path.read_text().splitlines()[ref["line"] - 1] == ref["text"]
    assert ref["code_head"] == code

b = read("before.json")
assert b["application_source_head"] == base and b["failing_subtests"] == 6
assert b["before_canonical_state_recorded"] is False
assert "FAILED (failures=6)" in (HERE / "before.log").read_text()
assert all(row["actual_detail_requests"] == 2 and row["expected_detail_requests"] == 1
           for row in b["scenarios"])
for name, count in (("directed.log", 62), ("regression.log", 1157)):
    text = (HERE / name).read_text()
    result = json.loads(text.splitlines()[-1])
    assert f"Ran {count} tests" in text
    assert result["tests_run"] == count and result["successful"]
    assert result["failures"] == result["errors"] == result["skipped"] == 0
    assert result["external_network_blocked"] and result["real_sdk_import_blocked"]
    assert result["repository_test_output_blocked"]
assert read("frozen-template-audit.json")["passed"] == 10
assert read("frozen-template-audit.json")["failed"] == 0
assert read("original-cli-gate.json")["passed"] == 3
assert read("original-cli-gate.json")["failed"] == 0
rows = read("after-cases.json")["cases"]
assert len(rows) == s["replay_cases"] == 20
assert all(c["pending_ledger_other_source_unchanged"] for c in rows)
for row in rows:
    assert row["budget_total_work_reserve"] == [270, 210, 60]
    if row["status"] == 503:
        assert row["canonical_unchanged"] and row["last_success_clock_unchanged"]
    if "_HTTP_" in row["case"]:
        assert row["status"] == 503 and row["detail_requests"] == 1
    if row["case"] in {"warmup_marker", "warmup_403"}:
        assert row["detail_requests"] == 0 and row["search_calls"] >= 2
    if row["case"] == "other_host":
        assert row["detail_hosts"] == ["www.ccgp.gov.cn", "ccgp.gov.cn"] and row["parser_calls"] == 1
    if row["case"].startswith("ordinary_"):
        assert row["detail_requests"] == 2
assert s["apply_allowed"] is s["migration_usable"] is False
state = json.loads((ROOT / "docs/project/checkpoint.json").read_text())
assert state["latest_code_validated_head"] == state["final_code_head"] == code
assert state["regional_runtime_r1_access_stop"]["python_tests_passed"] == 1157
assert state["regional_runtime_r1_access_stop"]["deployed"] is False
changed = set(git("diff", "--name-only", code).decode().splitlines())
untracked = set(git("ls-files", "--others", "--exclude-standard").decode().splitlines())
allowed = {"docs/project/current-state.md", "docs/project/checkpoint.json", "docs/project/next-task.md",
           "docs/project/runtime-regional-access-stop-2026-11-07.md"}
prefix = "docs/project/validation/runtime-regional-access-stop-2026-11-07/"
assert all(path in allowed or path.startswith(prefix) for path in changed | untracked)
subprocess.run(["git", "diff", "--check", base], cwd=ROOT, check=True)
assert read("completion.json")["within_foreground_deadline"]
for path, digest in read("manifest.json")["sha256"].items():
    assert sha((ROOT / path).read_bytes()) == digest, path
print("PASS: 2 authorized files; regional-only AST change; 12 new/62 directed/1157 Python/10/3; "
      "6 before subcases and 20 after replays; 528 protected and 453 unchanged files; offline scope")
