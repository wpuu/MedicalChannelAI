"""Static contract/evidence checks only; no application, SDK or test imports."""
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(name):
    return json.loads((HERE / name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def function(tree, name):
    return next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


s = read("validation-summary.json")
base, code = s["starting_head"], s["unchanged_code_head"]
assert git("branch", "--show-current") == "codex/p0-reliability-contracts"
subprocess.run(["git", "merge-base", "--is-ancestor", code, base], cwd=ROOT, check=True)
assert all(p.startswith("docs/project/") for p in git("diff", "--name-only", code, base).splitlines())
p = read("input-integrity.json")
assert len(p["files"]) == p["protected_file_count"] == s["protected_files"] == 545
for path, expected in p["files"].items():
    assert sha(ROOT / path) == expected, path
boundaries = read("unchanged-boundaries.json")
assert len(boundaries) == s["unchanged_web_workflow_files"] == 455
for path, expected in boundaries.items():
    assert sha(ROOT / path) == expected, path
refs = read("source-references.json")
assert len(refs) == s["source_references"] == 30
for r in refs:
    path = ROOT / r["path"]
    assert sha(path) == r["sha256"]
    assert path.read_text().splitlines()[r["line"] - 1] == r["text"]
    assert r["code_head"] == code and r["reviewed_repository_head"] == base
report = ROOT / "docs/project/ccgp-event-stage-budget-contract-2026-11-07.md"
links = {((report.parent / p).resolve().relative_to(ROOT).as_posix(), int(n))
         for p, n in re.findall(r"\]\(([^)]+)#L(\d+)\)", report.read_text())}
assert links == {(r["path"], r["line"]) for r in refs}

runtime = ast.parse((ROOT / "web/collector_runtime.py").read_text())
query = ast.parse((ROOT / "web/pipeline/scripts/sync_ccgp_query.py").read_text())
regional = ast.parse((ROOT / "web/pipeline/scripts/sync_regional_ccgp.py").read_text())
plan = json.loads((ROOT / "web/pipeline/data/tianjin_query_plan.json").read_text())
scan = function(query, "scan_events")
batch = function(runtime, "_run_event_batch")
assert "budget" not in [a.arg for a in scan.args.args + scan.args.kwonlyargs]
assert "budget" not in [a.arg for a in batch.args.args + batch.args.kwonlyargs]
assert any(isinstance(n, ast.ImportFrom) and n.module == "sync_ccgp_query" for n in regional.body)
assert not any(isinstance(n, ast.ImportFrom) and n.module == "sync_regional_ccgp" for n in query.body)
kinds = ast.literal_eval(next(n.iter for n in scan.body if isinstance(n, ast.For)))
assert kinds == (("更正公告", "CORRECTION"), ("终止公告", "TERMINATION"))
model = read("capacity-model.json")
assert model["batch_size"] == 5 and model["registered_watch_capacity"] == 30
assert model["default_plan_watch_cap"] == plan["max_event_watch_projects"] == 30
assert model["default_delay_seconds"] == plan["delay_seconds"] == 4
assert 5 * len(kinds) * (30 + plan["delay_seconds"]) == model["nominal_parameter_sum_no_details"] == 340
assert model["fixed_sleep_per_full_batch_without_details"] == 40
assert model["nominal_extra_per_detail"] == 34
assert model["actual_latency_measured"] is model["full_default_completion_guaranteed"] is False
assert json.loads((ROOT / "web/vercel.json").read_text())["functions"]["api/collector-queue.py"]["maxDuration"] == 300
assert "not 1 <= max_event_watch_projects <= 100" in (ROOT / "web/pipeline/scripts/sync_tianjin_plan.py").read_text()
calls = [n for n in ast.walk(batch) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_cache_set"]
assert len(calls) == 2
assert {ast.unparse(n.args[1]) for n in calls} == {"CCGP_COMMITTED_STATE_KEY", "CCGP_CYCLE_STAGING_KEY"}

contract = read("proposed-contract.json")
assert contract["status"] == "PROPOSED_NOT_IMPLEMENTED"
assert [contract[k] for k in ("total_seconds", "work_seconds", "batch_data_save_seconds", "tail_reserve_seconds")] == [270, 180, 30, 60]
assert 180 + 30 + 60 == 270
assert len(contract["new_code_files_requested"]) == 6
assert contract["new_code_authorized_this_round"] is False
decision = read("decision.json")
assert decision["automatic_continuation"] == "BLOCKED_PENDING_EXPLICIT_SIX_FILE_AUTHORIZATION"
assert contract["new_code_files_requested"] == decision["additional_code_files_need_authorization"]
assert decision["strong_guarantees_and_sdk"] == "CLOSED_NO_GO"
prior_path = ROOT / "docs/project/validation/runtime-regional-access-stop-2026-11-07/validation-summary.json"
assert sha(prior_path) == s["historical_validation_sha256"]
prior = json.loads(prior_path.read_text())
assert prior["code_head"] == code
assert [prior[k] for k in ("python_tests_passed", "frozen_template_passed", "original_cli_passed")] == s["historical_python_frozen_cli"] == [1157, 10, 3]
assert s["historical_tests_rerun"] is s["application_or_sdk_executed"] is False
state = json.loads((ROOT / "docs/project/checkpoint.json").read_text())
assert state["latest_code_validated_head"] == state["final_code_head"] == code
assert state["ccgp_event_stage_budget_contract"]["next_code_authorized"] is False
assert state["current_authorization_scope"]["application_or_test_code_this_round"] is False
for item in (s, contract, decision):
    assert item["apply_allowed"] is item["migration_usable"] is False
allowed = {"docs/project/current-state.md", "docs/project/checkpoint.json", "docs/project/next-task.md",
           "docs/project/ccgp-event-stage-budget-contract-2026-11-07.md"}
prefix = "docs/project/validation/ccgp-event-stage-budget-contract-2026-11-07/"
changes = set(git("diff", "--name-only", base).splitlines()) | set(git("ls-files", "--others", "--exclude-standard").splitlines())
assert all(path in allowed or path.startswith(prefix) for path in changes), changes
subprocess.run(["git", "diff", "--check", base], cwd=ROOT, check=True)
assert read("completion.json")["within_foreground_deadline"]
for path, expected in read("manifest.json")["sha256"].items():
    assert sha(ROOT / path) == expected, path
print("PASS: docs-only;30 source refs;545 protected/455 unchanged source-config files;"
      "340s parameter arithmetic; proposed270/180/30/60;1157/10/3 historical only;"
      "six-file implementation awaits explicit authorization;apply_allowed=migration_usable=false")
