from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .collector_core import SCHEMA_VERSION


DEFAULT_MODEL_FACT_LIMIT = 24
DEFAULT_MODEL_FACT_CHAR_LIMIT = 12000


@dataclass(frozen=True)
class QueryBudgets:
    max_db_candidates: int
    max_deterministic_match_candidates: int
    max_deep_enrichment_candidates: int
    max_model_candidates: int
    max_final_action_cards: int
    max_live_source_requests: int
    max_model_facts_per_opportunity: int
    max_model_fact_chars_per_opportunity: int

    def as_dict(self) -> dict[str, int]:
        return {
            "max_db_candidates": self.max_db_candidates,
            "max_deterministic_match_candidates": self.max_deterministic_match_candidates,
            "max_deep_enrichment_candidates": self.max_deep_enrichment_candidates,
            "max_model_candidates": self.max_model_candidates,
            "max_final_action_cards": self.max_final_action_cards,
            "max_live_source_requests": self.max_live_source_requests,
            "max_model_facts_per_opportunity": self.max_model_facts_per_opportunity,
            "max_model_fact_chars_per_opportunity": self.max_model_fact_chars_per_opportunity,
        }


INTERACTIVE_NORMAL = QueryBudgets(500, 200, 30, 10, 5, 0, DEFAULT_MODEL_FACT_LIMIT, DEFAULT_MODEL_FACT_CHAR_LIMIT)
INTERACTIVE_WIDE = QueryBudgets(500, 200, 24, 8, 5, 0, DEFAULT_MODEL_FACT_LIMIT, DEFAULT_MODEL_FACT_CHAR_LIMIT)
INTERACTIVE_VERY_WIDE = QueryBudgets(500, 150, 15, 5, 5, 0, 20, 10000)
DEEP_DIVE = QueryBudgets(20, 10, 1, 1, 1, 3, 32, 16000)
SCHEDULED_REFRESH = QueryBudgets(5000, 0, 0, 0, 0, 250, 1, 1)


def _region_selector_count(profile: dict[str, Any]) -> int:
    count = 0
    for region in profile.get("operating_regions") or []:
        if not isinstance(region, dict):
            continue
        if region.get("scope_mode") == "SELECTED_DISTRICTS":
            districts = {item for item in region.get("districts") or [] if isinstance(item, str) and item.strip()}
            count += max(1, len(districts))
        else:
            count += 1
    return max(1, count)


def _taxonomy_ids(profile: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for capability in profile.get("product_capabilities") or []:
        if not isinstance(capability, dict):
            continue
        for taxonomy_id in capability.get("taxonomy_ids") or []:
            if isinstance(taxonomy_id, str) and taxonomy_id.strip():
                result.add(taxonomy_id.strip())
    return result


def _scope_class(region_count: int, taxonomy_count: int) -> tuple[str, int]:
    # Width/risk indicator only. Runtime must NOT generate one live crawl for
    # every region x product cell. Public-data acquisition is source-driven and shared.
    cells = max(1, region_count) * max(1, taxonomy_count)
    if cells <= 24:
        return "NORMAL", cells
    if cells <= 120:
        return "WIDE", cells
    return "VERY_WIDE", cells


def _budgets(mode: str, scope_class: str) -> QueryBudgets:
    if mode == "SINGLE_OPPORTUNITY_DEEP_DIVE":
        return DEEP_DIVE
    if mode == "SCHEDULED_INDEX_REFRESH":
        return SCHEDULED_REFRESH
    if mode != "INTERACTIVE_DAILY":
        raise ValueError(f"unsupported query mode: {mode}")
    if scope_class == "VERY_WIDE":
        return INTERACTIVE_VERY_WIDE
    if scope_class == "WIDE":
        return INTERACTIVE_WIDE
    return INTERACTIVE_NORMAL


def build_query_execution_plan(
    profile: dict[str, Any],
    *,
    mode: str = "INTERACTIVE_DAILY",
) -> dict[str, Any]:
    region_count = _region_selector_count(profile)
    taxonomy_count = max(1, len(_taxonomy_ids(profile)))
    scope_class, scope_cells = _scope_class(region_count, taxonomy_count)
    budgets = _budgets(mode, scope_class)

    warnings: list[str] = []
    if mode == "INTERACTIVE_DAILY":
        warnings.append("LIVE_CRAWL_DISABLED_FOR_INTERACTIVE_PROFILE_QUERY")
        warnings.append("MODEL_CONTEXT_IS_BOUNDED_PER_OPPORTUNITY")
    if scope_class == "WIDE":
        warnings.append("WIDE_PROFILE_SCOPE_USE_SUMMARY_THEN_DRILL_DOWN")
    elif scope_class == "VERY_WIDE":
        warnings.append("VERY_WIDE_PROFILE_SCOPE_STRICT_TOP_N_AND_BATCHING_REQUIRED")
    if mode == "SCHEDULED_INDEX_REFRESH":
        warnings.append("INDEX_REFRESH_IS_SOURCE_DRIVEN_NOT_CUSTOMER_CARTESIAN_QUERY")

    stages = [
        {
            "stage": "FACT_INDEX_FILTER",
            "strategy": "Filter the shared VERIFIED fact index using OR predicates and database indexes; do not re-crawl per profile dimension.",
            "limit": budgets.max_db_candidates,
        },
        {
            "stage": "DETERMINISTIC_MATCH",
            "strategy": "Apply profile, region, institution, taxonomy, stage, amount, rental and exclusion rules before any model call.",
            "limit": budgets.max_deterministic_match_candidates,
        },
        {
            "stage": "DEEP_ENRICHMENT",
            "strategy": "Fetch/parse missing official detail or attachments only for top candidates that still need evidence.",
            "limit": budgets.max_deep_enrichment_candidates,
        },
        {
            "stage": "MODEL_DECISION",
            "strategy": "Send only bounded grounded facts for one opportunity at a time; never send the whole candidate corpus in one prompt.",
            "limit": budgets.max_model_candidates,
        },
        {
            "stage": "FINAL_ACTIONS",
            "strategy": "Return the highest-priority actionable cards; preserve lower-ranked matches for browse/search rather than expanding the model context.",
            "limit": budgets.max_final_action_cards,
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "scope_class": scope_class,
        "acquisition_strategy": "SHARED_FACT_INDEX_NOT_PER_PROFILE_CRAWL",
        "profile_scope": {
            "region_selector_count": region_count,
            "taxonomy_id_count": taxonomy_count,
            "scope_cells": scope_cells,
        },
        "budgets": budgets.as_dict(),
        "execution_stages": stages,
        "warnings": warnings,
    }
