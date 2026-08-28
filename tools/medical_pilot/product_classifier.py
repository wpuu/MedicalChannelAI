from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .collector_core import normalize_space


TAXONOMY_PATH = Path(__file__).with_name("product_taxonomy.v0.1.json")
CLASSIFIER_ID = "deterministic-product-taxonomy-v0.1"

SUPPRESSION_RULES = {
    "MEDICAL_IMAGING_SPECT_CT": {"MEDICAL_IMAGING_CT"},
    "LAB_REAGENT_FLOW_CYTOMETRY": {"LAB_REAGENT_GENERAL"},
    "LAB_REAGENT_MOLECULAR": {"LAB_REAGENT_GENERAL"},
    "LAB_REAGENT_IMMUNOASSAY": {"LAB_REAGENT_GENERAL"},
}


@dataclass(frozen=True)
class ProductClassification:
    labels: tuple[str, ...]
    validation_status: str
    supporting_fact_ids: tuple[str, ...]
    matched_phrases: dict[str, tuple[str, ...]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "taxonomy_version": "0.1",
            "labels": list(self.labels),
            "provenance": "DETERMINISTIC",
            "validation_status": self.validation_status,
            "supporting_fact_ids": list(self.supporting_fact_ids),
            "matched_phrases": {key: list(value) for key, value in self.matched_phrases.items()},
            "classifier_id": CLASSIFIER_ID,
        }


def _load_taxonomy(path: Path = TAXONOMY_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    labels = payload.get("labels")
    if not isinstance(labels, list):
        raise ValueError("taxonomy labels missing")
    return [item for item in labels if isinstance(item, dict)]


def taxonomy_ids(path: Path = TAXONOMY_PATH) -> frozenset[str]:
    return frozenset(
        item["id"]
        for item in _load_taxonomy(path)
        if isinstance(item.get("id"), str) and item["id"]
    )


def taxonomy_label_exists(label: str, path: Path = TAXONOMY_PATH) -> bool:
    return isinstance(label, str) and label in taxonomy_ids(path)


def _norm(value: str) -> str:
    return (
        normalize_space(value)
        .lower()
        .replace("（", "(")
        .replace("）", ")")
        .replace("／", "/")
    )


def classify_product_facts(
    facts: list[dict[str, Any]],
    *,
    taxonomy_path: Path = TAXONOMY_PATH,
) -> ProductClassification:
    verified_texts: list[tuple[str, str]] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if fact.get("fact_type") != "OFFICIAL_PUBLIC_FACT":
            continue
        if fact.get("verification_status") != "VERIFIED":
            continue
        if fact.get("model_generated") is not False:
            continue
        fact_id = fact.get("fact_id")
        value = fact.get("field_value")
        if not isinstance(fact_id, str) or not isinstance(value, str) or not value.strip():
            continue
        verified_texts.append((fact_id, _norm(value)))

    matched: dict[str, set[str]] = {}
    supporting: dict[str, set[str]] = {}
    taxonomy = _load_taxonomy(taxonomy_path)
    taxonomy_order = [str(item.get("id")) for item in taxonomy]

    for item in taxonomy:
        label = item.get("id")
        phrases = item.get("deterministic_phrases")
        if not isinstance(label, str) or not isinstance(phrases, list):
            continue
        for phrase in phrases:
            if not isinstance(phrase, str) or not phrase:
                continue
            normalized_phrase = _norm(phrase)
            for fact_id, text in verified_texts:
                if normalized_phrase in text:
                    matched.setdefault(label, set()).add(phrase)
                    supporting.setdefault(label, set()).add(fact_id)

    labels = set(matched)
    for specific, suppressed in SUPPRESSION_RULES.items():
        if specific in labels:
            labels.difference_update(suppressed)
            for dropped in suppressed:
                matched.pop(dropped, None)
                supporting.pop(dropped, None)

    ordered_labels = tuple(label for label in taxonomy_order if label in labels)
    supporting_fact_ids = tuple(
        sorted({fact_id for label in ordered_labels for fact_id in supporting.get(label, set())})
    )
    matched_phrases = {
        label: tuple(sorted(matched.get(label, set())))
        for label in ordered_labels
    }

    return ProductClassification(
        labels=ordered_labels,
        validation_status="VALIDATED" if ordered_labels else "UNVERIFIED",
        supporting_fact_ids=supporting_fact_ids,
        matched_phrases=matched_phrases,
    )


def apply_product_classification(
    opportunity: dict[str, Any],
    classification: ProductClassification,
) -> dict[str, Any]:
    result = dict(opportunity)
    result["product_labels"] = list(classification.labels)
    result["product_label_provenance"] = "DETERMINISTIC"
    result["product_label_validation_status"] = classification.validation_status
    return result
