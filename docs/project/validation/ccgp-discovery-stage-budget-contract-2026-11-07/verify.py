"""Static evidence validation only; never import application, SDK or tests."""
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


s = read("validation-summary.json")
base, code = s["starting_head"], s["unchanged_code_head"]
assert git("branch", "--show-current") == "codex/p0-reliability-contracts"
subprocess.run(["git", "merge-base", "--is-ancestor", code, base], cwd=ROOT, check=True)
assert all(p.startswith("docs/project/") for p in git("diff", "--name-only", code, base).splitlines())
integrity = read("input-integrity.json")
assert len(integrity["files"]) == integrity["protected_file_count"] == s["protected_files"] == 570
for path, expected in integrity["files"].items():
    assert sha(ROOT / path) == expected, path
boundaries = read("unchanged-boundaries.json")
assert len(boundaries) == s["unchanged_web_workflow_files"] == 455
for path, expected in boundaries.items():
    assert sha(ROOT / path) == expected, path
refs = read("source-references.json")
assert len(refs) == s["source_references"] == 20
for r in refs:
    path = ROOT / r["path"]
    assert sha(path) == r["sha256"] and path.read_text().splitlines()[r["line"] - 1] == r["text"]
    assert r["code_head"] == code and r["reviewed_repository_head"] == base
report = ROOT / "docs/project/ccgp-discovery-stage-budget-contract-2026-11-07.md"
links = {((report.parent / path).resolve().relative_to(ROOT).as_posix(), int(n))
         for path, n in re.findall(r"\]\(([^)]+)#L(\d+)\)", report.read_text())}
assert links == {(r["path"], r["line"]) for r in refs}
plan = json.loads((ROOT / "web/pipeline/data/tianjin_query_plan.json").read_text())
k, t, d, n = len(plan["keywords"]), len(plan["notice_types"]), plan["delay_seconds"], plan["max_candidates"]
assert [k, t, d, n] == [5, 2, 4, 12]
fixed = k * (t - 1) * d + (k - 1) * d
model = read("capacity-model.json")
assert fixed == model["discovery_fixed_wait"] == 36
assert fixed + n * d == model["full_fixed_wait"] == 84
assert k * t * 30 + fixed == model["nominal_no_details"] == 336
assert (k * t + n) * 30 + fixed + n * d == model["nominal_full_parameter_sum"] == 744
assert model["is_real_latency_measurement"] is model["full_default_on_time_guaranteed"] is False
tree = ast.parse((ROOT / "web/collector_runtime.py").read_text())
function = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "_run_ccgp")
assert "budget" not in [a.arg for a in function.args.args + function.args.kwonlyargs]
observed = read("static-observations.json")
assert observed["selected_slice"] == ["discovered[:plan['max_candidates']]"]
assert [r["key"] for r in observed["preparation_cache_sets"]] == ["CCGP_CYCLE_STAGING_KEY", "CCGP_WATCH_KEY"]
assert observed["direct_cache_gets"][0]["args"] == ["CCGP_COMMITTED_STATE_KEY"]
assert len(observed["direct_cache_gets"]) == 1 and observed["bootstrap_helper_calls"] == 2
assert "len(discovered) >" not in ast.unparse(function)
contract, decision = read("proposed-contract.json"), read("decision.json")
assert contract["status"] == "PROPOSED_NOT_IMPLEMENTED"
assert contract["total_work_dual_prepare_tail"] == [270, 150, 60, 60]
assert 150 + 60 + 60 == 270 and contract["primitive_finalize_reserve_seconds"] == 120
assert contract["prepare_order"] == ["STAGING_WRITE", "STAGING_READBACK_MATCH", "WATCH_WRITE", "WATCH_READBACK_MATCH"]
assert contract["new_existing_files_requested"] == decision["new_files_requested"]
assert len(contract["new_existing_files_requested"]) == 5
assert contract["ccgp_code_authorized_this_round"] is False
assert decision["goal_continuation"] == "BLOCKED_PENDING_EXPLICIT_CCGP_STAGE_AUTHORIZATION"
prior_path = ROOT / "docs/project/validation/ccgp-event-stage-budget-implementation-2026-11-07/validation-summary.json"
assert sha(prior_path) == s["historical_validation_sha256"]
prior = json.loads(prior_path.read_text())
assert prior["code_head"] == code
assert [prior[k] for k in ("python_tests_passed", "frozen_template_passed", "original_cli_passed")] == s["historical_python_frozen_cli"] == [1181, 10, 3]
assert s["tests_rerun"] is s["application_or_sdk_executed"] is False
state = json.loads((ROOT / "docs/project/checkpoint.json").read_text())
assert state["latest_code_validated_head"] == state["final_code_head"] == code
assert state["ccgp_discovery_stage_budget_contract"]["next_ccgp_code_authorized"] is False
for item in (s, contract, decision):
    assert item["apply_allowed"] is item["migration_usable"] is False
allowed = {"docs/project/current-state.md", "docs/project/checkpoint.json", "docs/project/next-task.md",
           "docs/project/ccgp-discovery-stage-budget-contract-2026-11-07.md"}
prefix = "docs/project/validation/ccgp-discovery-stage-budget-contract-2026-11-07/"
changes = set(git("diff", "--name-only", base).splitlines()) | set(git("ls-files", "--others", "--exclude-standard").splitlines())
assert all(path in allowed or path.startswith(prefix) for path in changes)
subprocess.run(["git", "diff", "--check", base], cwd=ROOT, check=True)
assert read("completion.json")["within_foreground_deadline"]
for path, expected in read("manifest.json")["sha256"].items():
    assert sha(ROOT / path) == expected, path
print("PASS: docs-only;20 source refs;570 protected/455 unchanged;336/744 nominal arithmetic;"
      "proposed270/150/60/60;1181/10/3 historical only;ccgp code scope awaits authorization")
