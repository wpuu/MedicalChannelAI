from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping

from .agnes_client import DEFAULT_BASE_URL, validate_base_url
from .pilot_api import CanonicalOriginPolicy


CANONICAL_ORIGIN_ENV = "MCAI_CANONICAL_ORIGIN"
AGNES_API_KEY_ENV = "MCAI_AGNES_API_KEY"
AGNES_BASE_URL_ENV = "MCAI_AGNES_BASE_URL"
VALID_ROLES = {"api", "worker", "all"}


@dataclass(frozen=True)
class PreflightCheck:
    check_id: str
    status: str
    error_code: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        value: dict[str, str | None] = {
            "check_id": self.check_id,
            "status": self.status,
        }
        if self.error_code is not None:
            value["error_code"] = self.error_code
        return value


def _pass(check_id: str) -> PreflightCheck:
    return PreflightCheck(check_id=check_id, status="PASS")


def _fail(check_id: str, error_code: str) -> PreflightCheck:
    return PreflightCheck(check_id=check_id, status="FAIL", error_code=error_code)


def _check_database_path(db_path: Path) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    path = Path(db_path)
    if not path.is_absolute():
        return [_fail("database_path", "DATABASE_PATH_MUST_BE_ABSOLUTE")]
    checks.append(_pass("database_path"))

    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        return checks + [_fail("database_parent", "DATABASE_PARENT_MISSING")]
    if not os.access(parent, os.W_OK | os.X_OK):
        return checks + [_fail("database_parent", "DATABASE_PARENT_NOT_WRITABLE")]
    checks.append(_pass("database_parent"))

    if path.exists():
        if not path.is_file():
            checks.append(_fail("database_file", "DATABASE_PATH_NOT_FILE"))
        elif not os.access(path, os.R_OK | os.W_OK):
            checks.append(_fail("database_file", "DATABASE_FILE_NOT_READ_WRITE"))
        else:
            checks.append(_pass("database_file"))
    else:
        checks.append(_pass("database_file"))
    return checks


def run_preflight(
    *,
    role: str,
    db_path: Path,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    if role not in VALID_ROLES:
        raise ValueError("role must be api, worker or all")
    env = os.environ if environ is None else environ
    checks = _check_database_path(Path(db_path))

    if role in {"api", "all"}:
        raw_origin = (env.get(CANONICAL_ORIGIN_ENV) or "").strip()
        if not raw_origin:
            checks.append(_fail("canonical_origin", "CANONICAL_ORIGIN_MISSING"))
        else:
            try:
                CanonicalOriginPolicy.parse(raw_origin)
            except ValueError:
                checks.append(_fail("canonical_origin", "CANONICAL_ORIGIN_INVALID"))
            else:
                checks.append(_pass("canonical_origin"))

    if role in {"worker", "all"}:
        api_key = (env.get(AGNES_API_KEY_ENV) or "").strip()
        if not api_key:
            checks.append(_fail("agnes_api_key", "AGNES_API_KEY_MISSING"))
        else:
            checks.append(_pass("agnes_api_key"))

        raw_base_url = (env.get(AGNES_BASE_URL_ENV) or "").strip() or DEFAULT_BASE_URL
        try:
            validate_base_url(raw_base_url)
        except ValueError:
            checks.append(_fail("agnes_base_url", "AGNES_BASE_URL_INVALID"))
        else:
            checks.append(_pass("agnes_base_url"))

    passed = all(check.status == "PASS" for check in checks)
    return {
        "schema_version": "0.1",
        "status": "PASS" if passed else "FAIL",
        "role": role,
        "checks": [check.as_dict() for check in checks],
        "secrets_echoed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-fast configuration and filesystem preflight for the real MedicalChannelAI Pilot host."
    )
    parser.add_argument("--role", choices=sorted(VALID_ROLES), required=True)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()

    result = run_preflight(role=args.role, db_path=args.db)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
