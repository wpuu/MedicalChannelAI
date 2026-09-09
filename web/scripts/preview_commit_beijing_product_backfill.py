from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web"
PIPELINE_ROOT = WEB_ROOT / "pipeline"
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline.ccgp_detail import (  # noqa: E402
    fetch_ccgp_detail_html,
    parse_ccgp_public_tender_html,
)

REGIONAL_PATH = PIPELINE_ROOT / "data" / "regional_live_ccgp_records.json"
PUBLIC_PATH = WEB_ROOT / "public" / "data" / "today-actions.public.json"
WORKFLOW_PATH = ".github/workflows/preview-commit-beijing-product-backfill.yml"
SCRIPT_PATH = "web/scripts/preview_commit_beijing_product_backfill.py"
EXPECTED_CHANGED = {
    "web/pipeline/data/regional_live_ccgp_records.json",
    "web/public/data/today-actions.public.json",
}
EXPECTED_UNSUPPORTED = {
    "ccgp_bj_10b27e7271e3637c",
    "ccgp_bj_27c4b67032bf597f",
    "ccgp_bj_1d41464508071bc8",
    "ccgp_bj_877131eb9f02f595",
    "ccgp_bj_2f3215759c2a7852",
}
EXPECTED_PRODUCTS = {
    "ccgp_bj_7288c338a1406922": ["医责险采购", "医师险采购"],
    "ccgp_bj_71b6984cdeed7b23": ["离心机", "全自动干式生化分析仪", "生物显微镜"],
    "ccgp_bj_6f5e872d1d6e7fa0": [
        "X射线骨密度检测仪",
        "磁共振成像系统",
        "乳腺X射线机",
        "医用磁共振成像系统（MR）",
        "数字乳腺X射线摄影系统",
        "X射线计算机体层摄影设备(CT)",
        "单光子发射及X射线计算机断层成像系统（SPECT/CT）",
    ],
    "ccgp_bj_bda3420ecd1d653d": [
        "超脉冲点阵手术激光系统",
        "上下肢主被动康复训练仪",
        "血流动力学监测平台",
        "便携式彩色超声诊断系统",
    ],
}
BAD_PREFIXES = ("备注", "注解", "项目用途", "项目现场", "保险期限", "合同履行期限", "服务期限")
BAD_EXACT = {"1年", "医院服务", "北京中医药大学东方医院指定地点"}


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def reparse_beijing(records: list[dict]) -> dict:
    targets = [
        (idx, record)
        for idx, record in enumerate(records)
        if (record.get("facts") or {}).get("market_code") == "BJ"
        and (record.get("facts") or {}).get("notice_type") == "公开招标公告"
        and not ((record.get("facts") or {}).get("product_items") or [])
    ]
    if len(targets) != 27:
        raise SystemExit(f"UNEXPECTED_BJ_EMPTY_TARGET_COUNT:{len(targets)}")

    recovered: list[dict] = []
    unsupported: list[dict] = []
    failures: list[dict] = []
    for position, (index, record) in enumerate(targets):
        if position:
            time.sleep(4.0)
        facts = record["facts"]
        source = record["source"]
        url = source["url"]
        try:
            html = fetch_ccgp_detail_html(url)
            fresh_record = parse_ccgp_public_tender_html(
                html,
                source_url=url,
                observed_at=source["observed_at"],
                opportunity_id=record["opportunity_id"],
            )
            fresh = fresh_record["facts"]
            if norm(fresh.get("project_number")) != norm(facts.get("project_number")):
                raise ValueError("PROJECT_NUMBER_MISMATCH")
            if norm(fresh.get("project_name")) != norm(facts.get("project_name")):
                raise ValueError("PROJECT_NAME_MISMATCH")
            items = fresh.get("product_items") or []
            names = [norm(item.get("raw_name")) for item in items]
            leaked = [name for name in names if name.startswith(BAD_PREFIXES) or name in BAD_EXACT]
            if leaked:
                raise ValueError("PRODUCT_METADATA_LEAK:" + "|".join(leaked))
            if not items:
                unsupported.append(
                    {
                        "opportunity_id": record["opportunity_id"],
                        "project_name": facts.get("project_name"),
                        "buyer_name": facts.get("buyer_name"),
                        "url": url,
                    }
                )
                continue

            facts["product_items"] = items
            facts["product_categories"] = fresh.get("product_categories") or []
            product_evidence = [
                item
                for item in fresh_record.get("evidence", [])
                if item.get("field_path") in {"facts.product_items", "facts.product_categories"}
            ]
            if not any(item.get("field_path") == "facts.product_items" for item in product_evidence):
                raise ValueError("PRODUCT_EVIDENCE_MISSING")
            record["evidence"] = [
                item
                for item in record.get("evidence", [])
                if item.get("field_path") not in {"facts.product_items", "facts.product_categories"}
            ] + product_evidence
            records[index] = record
            recovered.append(
                {
                    "opportunity_id": record["opportunity_id"],
                    "project_name": facts.get("project_name"),
                    "buyer_name": facts.get("buyer_name"),
                    "url": url,
                    "item_count": len(items),
                    "items": names,
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "opportunity_id": record.get("opportunity_id"),
                    "project_name": facts.get("project_name"),
                    "buyer_name": facts.get("buyer_name"),
                    "url": url,
                    "error": type(exc).__name__,
                    "message": str(exc)[:500],
                }
            )

    unsupported_ids = {row["opportunity_id"] for row in unsupported}
    if failures:
        raise SystemExit("BJ_BACKFILL_HAS_TRUE_FAILURES:" + json.dumps(failures, ensure_ascii=False))
    if len(recovered) != 22:
        raise SystemExit(f"UNEXPECTED_RECOVERED_COUNT:{len(recovered)}")
    if unsupported_ids != EXPECTED_UNSUPPORTED:
        raise SystemExit("UNEXPECTED_UNSUPPORTED_SET:" + json.dumps(sorted(unsupported_ids), ensure_ascii=False))

    recovered_by_id = {row["opportunity_id"]: row for row in recovered}
    for opportunity_id, expected in EXPECTED_PRODUCTS.items():
        actual = (recovered_by_id.get(opportunity_id) or {}).get("items")
        if actual != expected:
            raise SystemExit(
                f"KNOWN_PRODUCT_SET_MISMATCH:{opportunity_id}:expected={expected!r}:actual={actual!r}"
            )

    return {
        "target_count": len(targets),
        "recovered_count": len(recovered),
        "unsupported_count": len(unsupported),
        "failure_count": len(failures),
        "recovered": recovered,
        "unsupported": unsupported,
        "failures": failures,
    }


def structured(cards: list[dict]) -> int:
    return sum(
        1
        for card in cards
        if (card.get("facts") or {}).get("lifecycle_state") == "BIDDING"
        and (
            (card.get("facts") or {}).get("product_items")
            or (card.get("facts") or {}).get("product_categories")
        )
    )


def verify_public_delta(baseline: dict, snapshot: dict, report: dict) -> None:
    old_pool = baseline.get("opportunity_pool") or []
    pool = snapshot.get("opportunity_pool") or []
    old_by_id = {str(card.get("opportunity_id") or ""): card for card in old_pool}
    by_id = {str(card.get("opportunity_id") or ""): card for card in pool}
    added_ids = sorted(set(by_id) - set(old_by_id))
    removed_ids = sorted(set(old_by_id) - set(by_id))

    leaks = []
    for card in pool:
        for item in (card.get("facts") or {}).get("product_items") or []:
            name = norm(item.get("raw_name"))
            if name.startswith(BAD_PREFIXES) or name in BAD_EXACT:
                leaks.append({"opportunity_id": card.get("opportunity_id"), "product": name})

    distribution = dict(sorted(Counter((card.get("facts") or {}).get("market_code") for card in pool).items()))
    result = {
        "baseline_pool_count": len(old_pool),
        "public_pool_count": len(pool),
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "baseline_structured_bidding": structured(old_pool),
        "structured_bidding": structured(pool),
        "structure_gain": structured(pool) - structured(old_pool),
        "market_distribution": distribution,
        "metadata_leaks": leaks,
    }
    print("BJ_COMMIT_PUBLIC_DELTA=" + json.dumps(result, ensure_ascii=False, indent=2))

    if len(old_pool) != 90 or len(pool) != 92:
        raise SystemExit(f"PUBLIC_POOL_COUNT_MISMATCH:{len(old_pool)}->{len(pool)}")
    if set(added_ids) != {"ccgp_bj_6f5e872d1d6e7fa0", "ccgp_bj_bda3420ecd1d653d"}:
        raise SystemExit("UNEXPECTED_ADDED_SET:" + json.dumps(added_ids, ensure_ascii=False))
    if removed_ids:
        raise SystemExit("REMOVED_PUBLIC_OPPORTUNITIES:" + json.dumps(removed_ids, ensure_ascii=False))
    if leaks:
        raise SystemExit("PUBLIC_PRODUCT_METADATA_LEAK:" + json.dumps(leaks, ensure_ascii=False))
    if distribution != {"BJ": 16, "HE": 14, "HL": 22, "JL": 8, "LN": 6, "TJ": 26}:
        raise SystemExit("UNEXPECTED_MARKET_DISTRIBUTION:" + json.dumps(distribution, ensure_ascii=False))
    if "ccgp_bj_4f06004fe0a3f03f" in by_id:
        raise SystemExit("NONMEDICAL_METROLOGY_ENTERED_PUBLIC_POOL")
    if any("办公耗材" in norm((card.get("facts") or {}).get("project_name")) for card in pool):
        raise SystemExit("OFFICE_CONSUMABLES_ENTERED_PUBLIC_POOL")
    if report["failure_count"] != 0 or report["recovered_count"] != 22 or report["unsupported_count"] != 5:
        raise SystemExit("BACKFILL_COUNTS_CHANGED")


def api_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }


def api_call(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=api_headers(token), method=method)
    with urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def git_blob_sha(path: Path, mode: str) -> str:
    if mode == "120000" and path.is_symlink():
        content = os.readlink(path).encode("utf-8")
    else:
        content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def verify_only_expected_tracked_changes(token: str, repo: str, expected_head: str) -> tuple[str, str]:
    api = f"https://api.github.com/repos/{repo}"
    commit = api_call("GET", f"{api}/git/commits/{expected_head}", token)
    base_tree = commit["tree"]["sha"]
    tree = api_call("GET", f"{api}/git/trees/{base_tree}?recursive=1", token)
    if tree.get("truncated"):
        raise SystemExit("REMOTE_TREE_TRUNCATED")

    changed = set()
    for entry in tree.get("tree", []):
        if entry.get("type") != "blob":
            continue
        relative = entry["path"]
        local = REPO_ROOT / relative
        if not local.exists() and not local.is_symlink():
            changed.add(relative)
            continue
        if git_blob_sha(local, entry.get("mode") or "100644") != entry.get("sha"):
            changed.add(relative)

    print("TRACKED_CHANGES=" + ",".join(sorted(changed)))
    if changed != EXPECTED_CHANGED:
        raise SystemExit(f"UNEXPECTED_TRACKED_CHANGES:{sorted(changed)!r}")
    return api, base_tree


def atomic_commit(token: str, repo: str, branch: str, expected_head: str, api: str, base_tree: str) -> str:
    ref_name = quote(f"heads/{branch}", safe="/")
    ref = api_call("GET", f"{api}/git/ref/{ref_name}", token)
    actual_head = ref["object"]["sha"]
    if actual_head != expected_head:
        raise SystemExit(f"REMOTE_HEAD_CHANGED expected={expected_head} actual={actual_head}")

    tree_entries = []
    for relative in sorted(EXPECTED_CHANGED):
        file_path = REPO_ROOT / relative
        blob = api_call(
            "POST",
            f"{api}/git/blobs",
            token,
            {
                "content": base64.b64encode(file_path.read_bytes()).decode("ascii"),
                "encoding": "base64",
            },
        )
        tree_entries.append({"path": relative, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    for relative in [WORKFLOW_PATH, SCRIPT_PATH]:
        tree_entries.append({"path": relative, "mode": "100644", "type": "blob", "sha": None})

    new_tree = api_call("POST", f"{api}/git/trees", token, {"base_tree": base_tree, "tree": tree_entries})
    new_commit = api_call(
        "POST",
        f"{api}/git/commits",
        token,
        {
            "message": "data: backfill grounded Beijing product items",
            "tree": new_tree["sha"],
            "parents": [expected_head],
        },
    )
    api_call("PATCH", f"{api}/git/refs/{ref_name}", token, {"sha": new_commit["sha"], "force": False})
    return new_commit["sha"]


def main() -> None:
    token = os.environ["GH_TOKEN"]
    repo = os.environ["REPOSITORY"]
    branch = os.environ["BRANCH"]
    expected_head = os.environ["EXPECTED_HEAD"]

    baseline = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
    records = json.loads(REGIONAL_PATH.read_text(encoding="utf-8"))
    report = reparse_beijing(records)
    print("BJ_COMMIT_BACKFILL=" + json.dumps(report, ensure_ascii=False))
    REGIONAL_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    subprocess.run(["npm", "ci"], cwd=WEB_ROOT, check=True)
    subprocess.run(["npm", "run", "build"], cwd=WEB_ROOT, check=True)

    snapshot = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
    verify_public_delta(baseline, snapshot, report)
    api, base_tree = verify_only_expected_tracked_changes(token, repo, expected_head)
    commit_sha = atomic_commit(token, repo, branch, expected_head, api, base_tree)
    print("COMMITTED=" + commit_sha)


if __name__ == "__main__":
    main()
