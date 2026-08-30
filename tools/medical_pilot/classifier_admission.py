from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


REGISTRY_PATH = Path(__file__).with_name("product_classifier_registry.v0.1.json")


@dataclass(frozen=True)
class ClassifierAdmission:
    classifier_id: str
    kind: str
    model_id: str | None
    admission_status: str
    can_drive_matching: bool


def load_classifier_admissions(path: Path = REGISTRY_PATH) -> dict[str, ClassifierAdmission]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload.get("classifiers")
    if not isinstance(records, list):
        raise ValueError("classifier registry must contain classifiers array")
    result: dict[str, ClassifierAdmission] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        classifier_id = record.get("classifier_id")
        if not isinstance(classifier_id, str) or not classifier_id:
            continue
        if classifier_id in result:
            raise ValueError(f"duplicate classifier id: {classifier_id}")
        result[classifier_id] = ClassifierAdmission(
            classifier_id=classifier_id,
            kind=str(record.get("kind")),
            model_id=record.get("model_id") if isinstance(record.get("model_id"), str) else None,
            admission_status=str(record.get("admission_status")),
            can_drive_matching=record.get("can_drive_matching") is True,
        )
    return result


def classifier_can_drive_matching(classifier_id: str, expected_kind: str) -> tuple[bool, str]:
    admission = load_classifier_admissions().get(classifier_id)
    if admission is None:
        return False, "CLASSIFIER_NOT_REGISTERED"
    if admission.kind != expected_kind:
        return False, "CLASSIFIER_KIND_MISMATCH"
    if admission.admission_status != "VALIDATED" or not admission.can_drive_matching:
        return False, "CLASSIFIER_NOT_ADMITTED"
    return True, "VALIDATED"
