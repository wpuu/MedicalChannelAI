"""Recorded evidence/AST/hash checks only; no app, SDK or test execution."""
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


def function(tree, name):
    return next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def dump(node):
    return ast.dump(node, include_attributes=False)


s = read("validation-summary.json")
base, code = s["starting_head"], s["code_head"]
assert set(git("diff", "--name-only", base, code).decode().splitlines()) == set(s["authorized_files"])
for path, expected in s["source_sha256"].items():
    assert sha((ROOT / path).read_bytes()) == sha(git("show", f"{code}:{path}")) == expected
allowed = {"web/collector_runtime.py": {"_run_event_batch", "run_stage"},
           "web/collector_queue.py": {"process_collector_payload"},
           "web/pipeline/scripts/sync_ccgp_query.py": {"scan_events"}}
for path, names in allowed.items():
    before = ast.parse(git("show", f"{base}:{path}"))
    after = ast.parse((ROOT / path).read_text())
    def other(tree):
        return [dump(n) for n in tree.body if not (
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names)]
    assert other(before) == other(after), path
    if path.endswith("collector_queue.py"):
        old, new = function(before, "process_collector_payload"), function(after, "process_collector_payload")
        start = next(i for i, n in enumerate(old.body) if isinstance(n, ast.Try))
        assert isinstance(new.body[-1], ast.Try)
        assert [dump(n) for n in old.body[start:]] == [dump(n) for n in new.body[-1].body]
added = []
for path in s["authorized_files"]:
    if "/tests/" not in path:
        continue
    def tests(raw):
        return {n.name for n in ast.walk(ast.parse(raw)) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}
    before, after = tests(git("show", f"{base}:{path}")), tests((ROOT / path).read_text())
    assert before <= after
    added.extend(path + ":" + name for name in sorted(after - before))
assert added == s["new_test_methods"] and len(added) == s["new_behavior_tests"] == 24
integrity = read("input-integrity.json")
assert len(integrity["files"]) == integrity["protected_file_count"] == s["protected_files"] == 556
for path, expected in integrity["files"].items():
    assert sha((ROOT / path).read_bytes()) == expected, path
boundaries = read("unchanged-boundaries.json")
assert len(boundaries) == s["unchanged_other_web_workflow_files"] == 449
for path, expected in boundaries.items():
    assert sha((ROOT / path).read_bytes()) == expected, path
for r in read("source-references.json"):
    data = (ROOT / r["path"]).read_bytes()
    assert sha(data) == r["sha256"] and data.decode().splitlines()[r["line"] - 1] == r["text"]
for name, count in (("directed.log", 139), ("regression.log", 1181)):
    text = (HERE / name).read_text()
    result = json.loads(text.splitlines()[-1])
    assert f"Ran {count} tests" in text and result["tests_run"] == count
    assert result["successful"] and result["failures"] == result["errors"] == result["skipped"] == 0
assert read("frozen-template-audit.json")["passed"] == 10 and read("original-cli-gate.json")["passed"] == 3
cases = read("cases.json")
assert [len(cases[k]) for k in ("source_cases", "helper_cases", "queue_cases")] == [35, 13, 4]
for row in cases["source_cases"]:
    assert row["pending_unchanged"] and row["verified_sibling_staging_retained"] and not row["data_has_receipt"]
    if row["receipt"]["target"] == "COMMITTED_PAIR":
        assert row["staging_unchanged"]
    if row["mode"] in {"write_before", "write_after"}:
        assert row["receipt"]["outcome"] == "UNKNOWN" and row["receipt"]["mutation_possible"]
    if row["mode"] in {"write_late", "local_save_late"}:
        assert row["status"] == 200 and row["receipt"]["outcome"] == "CALL_RETURNED_UNVERIFIED"
        assert row["receipt"]["save_window_overrun"]
    if row["receipt"]["outcome"] == "NOT_ATTEMPTED":
        assert not row["writes"] and row["committed_unchanged"] and row["staging_unchanged"]
for row in cases["helper_cases"]:
    if "late" in row["mode"] or row["mode"] == "sleep_admission":
        assert row["error_phase"] and row["events"] is None and row["failure_count"] == 0
for row in cases["queue_cases"]:
    if row["error_type"]:
        assert row["diagnostics"]["event_write_receipt"]["outcome"] == "CALL_RETURNED_UNVERIFIED"
    if row["mode"] == "late":
        assert row["events"] == ["heartbeat", "heartbeat", "enqueue"]
assert s["total_work_batch_save_tail"] == [270, 180, 30, 60] and s["primitive_finalize_reserve_seconds"] == 90
assert s["apply_allowed"] is s["migration_usable"] is False
state = json.loads((ROOT / "docs/project/checkpoint.json").read_text())
assert state["latest_code_validated_head"] == state["final_code_head"] == code
assert state["ccgp_event_stage_budget_implementation"]["python_tests_passed"] == 1181
permitted = {"docs/project/current-state.md", "docs/project/checkpoint.json", "docs/project/next-task.md",
             "docs/project/ccgp-event-stage-budget-implementation-2026-11-07.md"}
prefix = "docs/project/validation/ccgp-event-stage-budget-implementation-2026-11-07/"
changed = set(git("diff", "--name-only", code).decode().splitlines()) | set(git("ls-files", "--others", "--exclude-standard").decode().splitlines())
assert all(path in permitted or path.startswith(prefix) for path in changed)
subprocess.run(["git", "diff", "--check", base], cwd=ROOT, check=True)
assert read("completion.json")["within_foreground_deadline"]
for path, expected in read("manifest.json")["sha256"].items():
    assert sha((ROOT / path).read_bytes()) == expected, path
print("PASS: six files;24 new/139 directed/1181 Python/10/3;35/13/4 cases;556 protected/449 unchanged;"
      "other functions and original Queue tail preserved;offline cooperative scope only")
