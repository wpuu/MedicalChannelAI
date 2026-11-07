"""Offline static evidence verifier; never imports application or test modules."""
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def read_json(name):
    return json.loads((HERE / name).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


bindings = read_json("version-bindings.json")
base, code = bindings["reviewed_head"], bindings["code_head"]
assert git("branch", "--show-current") == "codex/p0-reliability-contracts"
assert git("rev-parse", "a352b7a") == code
for commit in bindings["implementation_commits"].values():
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, base], cwd=ROOT, check=True)
assert all(path.startswith("docs/project/") for path in git("diff", "--name-only", code, base).splitlines())

refs = read_json("source-references.json")
for ref in refs:
    path = ROOT / ref["path"]
    assert digest(path) == ref["sha256"], ref["path"]
    assert path.read_text().splitlines()[ref["line"] - 1] == ref["text"]
    assert ref["reviewed_repository_head"] == base and ref["code_head"] == code
report = ROOT / "docs/project/runtime-reliability-closeout-2026-11-07.md"
actual_links = {
    ((report.parent / path).resolve().relative_to(ROOT).as_posix(), int(number))
    for path, number in re.findall(r"\]\(([^)]+)#L(\d+)\)", report.read_text())
}
assert actual_links == {(ref["path"], ref["line"]) for ref in refs}

integrity = read_json("input-integrity.json")
assert integrity["file_count"] == len(integrity["files"]) == 517
for row in integrity["files"]:
    path = ROOT / row["path"]
    assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], row["path"]

observed = read_json("static-source-observations.json")
runtime = ast.parse((ROOT / "web/collector_runtime.py").read_text())
regional = next(n for n in runtime.body if isinstance(n, ast.FunctionDef) and n.name == "_run_regional_market")
loop = next(n for n in ast.walk(regional) if isinstance(n, ast.For) and ast.unparse(n.iter) == "selected")
handler = next(h for n in loop.body if isinstance(n, ast.Try) for h in n.handlers
               if isinstance(h.type, ast.Name) and h.type.id == "Exception")
assert [ast.unparse(n) for n in handler.body] == observed["regional_detail_exception_statements"]
assert len(handler.body) == 1 and "failures.append" in ast.unparse(handler.body[0])
assert not any(isinstance(n, (ast.Break, ast.Raise)) for item in handler.body for n in ast.walk(item))
assert observed["regional_detail_exception_has_break_or_raise"] is False
assert "RATE_LIMIT_MARKERS" not in ast.unparse(regional)
assert observed["regional_has_rate_limit_markers_check"] is False
sessions = [n for n in ast.walk(regional) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "RegionalCcgpSearchSession"]
assert [[k.arg for k in n.keywords] for n in sessions] == observed["regional_session_keyword_sets"]
assert all("on_access_blocked" not in [k.arg for k in n.keywords] for n in sessions)
assert len(observed["deep_budgeted"]) == 11 and len(observed["deep_unbudgeted"]) == 14
assert len(observed["incremental_unbudgeted"]) == 7
assert len(observed["queue_budget_constructors"]) == 2
assert observed["shared_retry_after_consumption"]["matches"] == []
for name in observed["shared_retry_after_consumption"]["files"]:
    assert not re.search(r"Retry-After|retry_after", (ROOT / name).read_text(), re.I)

historical = bindings["historical_latest_validation"]
assert digest(ROOT / historical["path"]) == historical["sha256"]
prior = json.loads((ROOT / historical["path"]).read_text())
assert prior["code_head"] == code
assert [prior[k] for k in ("python_tests_passed", "frozen_template_passed", "original_cli_passed")] == [1145, 10, 3]
for path, expected in prior["source_sha256"].items():
    assert digest(ROOT / path) == expected

coverage = read_json("coverage-matrix.json")
gaps = read_json("remaining-gaps.json")
decision = read_json("next-decision.json")
summary = read_json("validation-summary.json")
assert len(coverage) == 11 and [gap["id"] for gap in gaps] == ["R1", "R2", "R3"]
assert decision["only_next_priority"] == summary["unique_next_priority"] == "R1"
assert decision["next_files"] == ["web/collector_runtime.py", "web/pipeline/tests/test_runtime_source_parity_behavior.py"]
assert summary["source_references_checked"] == len(refs) == 51
assert summary["tests_rerun"] is False and summary["new_behavior_tests"] == 0
assert summary["application_or_sdk_executed"] is False
assert decision["current_round_code_authorized"] is False
assert decision["apply_allowed"] is summary["apply_allowed"] is False
assert decision["migration_usable"] is summary["migration_usable"] is False
state = json.loads((ROOT / "docs/project/checkpoint.json").read_text())
assert state["latest_code_validated_head"] == state["final_code_head"] == code
assert state["runtime_reliability_closeout"]["unique_next_priority"] == "R1"
assert state["current_authorization_scope"]["application_or_tests_execution_this_round"] is False

allowed = {
    "docs/project/current-state.md", "docs/project/checkpoint.json", "docs/project/next-task.md",
    "docs/project/runtime-reliability-closeout-2026-11-07.md",
}
changed = set(git("diff", "--name-only", base).splitlines())
untracked = set(git("ls-files", "--others", "--exclude-standard").splitlines())
prefix = "docs/project/validation/runtime-reliability-closeout-2026-11-07/"
assert all(path in allowed or path.startswith(prefix) for path in changed | untracked), changed | untracked
subprocess.run(["git", "diff", "--check", base], cwd=ROOT, check=True)
manifest = read_json("manifest.json")
for item in manifest["files"]:
    assert digest(ROOT / item["path"]) == item["sha256"], item["path"]
assert read_json("completion.json")["within_foreground_deadline"] is True
print(json.dumps({"static_verification": "PASS", "source_references": len(refs),
                  "protected_files": len(integrity["files"]), "remaining_gaps": len(gaps),
                  "next_priority": "R1", "tests_executed": False,
                  "apply_allowed": False, "migration_usable": False}, ensure_ascii=False))
