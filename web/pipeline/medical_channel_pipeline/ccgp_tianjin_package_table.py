"""Strict extraction of a CCGP six-column clinical-lab procurement package table.

This adapter deliberately does not recognize arbitrary tender descriptions.
Only an official CCGP parser may call it, after verifying the source host,
project identity, tender type, dates and the official total budget.

The named items are explicit items in the main notice, not a complete BOM.
Quantities not stated in the official table must remain None.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any


_HEADERS = (
    "包号",
    "是否设置最高限价",
    "预算(万元)",
    "最高限价(万元)",
    "采购目录",
    "采购需求",
)
_ALLOWED_CATEGORY = "临床检验设备"
_MAX_PACKAGES = 20
_MAX_NAMES_PER_PACKAGE = 12
_MAX_TOTAL_ITEMS = 100


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")")


class _NestedTableReader(HTMLParser):
    """Read cells from simple tables, including a table within a content wrapper.

    A separate context is used for every nesting level: otherwise a 6-column
    purchase table inside an outer one-cell CMS table disappears during parse.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[dict[str, Any]] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "table":
            self._stack.append({"rows": [], "row": None, "cell": None})
            return
        if not self._stack:
            return
        ctx = self._stack[-1]
        if tag == "tr":
            ctx["row"] = []
        elif tag in {"td", "th"} and ctx["row"] is not None:
            ctx["cell"] = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth or not self._stack:
            return
        cell = self._stack[-1]["cell"]
        if cell is not None and data.strip():
            cell.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth or not self._stack:
            return
        ctx = self._stack[-1]
        if tag in {"td", "th"}:
            if ctx["cell"] is not None and ctx["row"] is not None:
                ctx["row"].append(" ".join(ctx["cell"]).strip())
            ctx["cell"] = None
        elif tag == "tr":
            if ctx["row"] is not None and any(ctx["row"]):
                ctx["rows"].append(ctx["row"])
            ctx["row"] = None
        elif tag == "table":
            done = self._stack.pop()
            if done["rows"]:
                self.tables.append(done["rows"])


def _cny_amount(raw: str) -> int | None:
    normalized = _normalize(raw).replace(",", "")
    if not re.fullmatch(r"\d{1,9}(?:\.\d{1,4})?", normalized):
        return None
    try:
        value = Decimal(normalized) * Decimal(10000)
    except InvalidOperation:
        return None
    if value <= 0 or value > 100_000_000_000 or value != value.to_integral_value():
        return None
    return int(value)


def _explicit_names(demand: str) -> tuple[list[str], bool] | None:
    """Only accept '采购<explicit names>等，具体内容详见项目需求书。'."""
    normalized = re.sub(r"\s+", "", demand)
    match = re.fullmatch(
        r"采购(?P<names>[^，,；;。:：]{3,500}?)等[，,]具体内容详见项目需求书[。.]?",
        normalized,
    )
    if match is None:
        return None
    names = match.group("names").split("、")
    if not 1 <= len(names) <= _MAX_NAMES_PER_PACKAGE:
        return None
    for name in names:
        if (
            len(name) < 3
            or len(name) > 90
            or re.search(r"(?:预算|最高限价|合同|资料|附件|采购需求|详见|项目)", name)
            or re.search(r"\d+(?:\.\d+)?(?:万元|元|台|套)", name)
        ):
            return None
    if len(set(names)) != len(names):
        return None
    return names, True


def extract_clinical_lab_package_table(
    html: str,
    *,
    expected_total_budget_cny: int | None,
    expected_total_ceiling_cny: int | None = None,
) -> list[dict[str, Any]]:
    """Return only complete, reconciled packages; otherwise fail closed with [].

    This function is called only on an already-authorized CCGP official page.
    Returned amounts are PACKAGE totals, never item-specific amounts.
    """
    if expected_total_budget_cny is None or expected_total_budget_cny <= 0:
        return []
    reader = _NestedTableReader()
    reader.feed(html)
    candidate_tables = [
        rows for rows in reader.tables
        if rows and tuple(_normalize(x) for x in rows[0]) == _HEADERS
    ]
    if len(candidate_tables) != 1:
        return []

    rows = candidate_tables[0]
    if not 2 <= len(rows) <= _MAX_PACKAGES + 1:
        return []
    packages: list[dict[str, Any]] = []
    for row in rows[1:]:
        if len(row) != len(_HEADERS):
            return []
        package_id, has_ceiling, raw_budget, raw_ceiling, raw_category, demand = row
        package_id = _normalize(package_id)
        number_match = re.fullmatch(r"第([1-9]\d?)包", package_id)
        if number_match is None:
            return []
        if int(number_match.group(1)) != len(packages) + 1:
            return []
        if _normalize(has_ceiling) != "是":
            return []
        category = _normalize(raw_category)
        if category != _ALLOWED_CATEGORY:
            return []
        budget = _cny_amount(raw_budget)
        ceiling = _cny_amount(raw_ceiling)
        if budget is None or ceiling is None or ceiling > budget:
            return []
        names_result = _explicit_names(demand)
        if names_result is None:
            return []
        names, non_exhaustive = names_result
        packages.append(
            {
                "package_id": package_id,
                "category": category,
                "budget_cny": budget,
                "ceiling_cny": ceiling,
                "product_names": names,
                "non_exhaustive": non_exhaustive,
            }
        )

    if sum(x["budget_cny"] for x in packages) != expected_total_budget_cny:
        return []
    if expected_total_ceiling_cny is not None:
        if sum(x["ceiling_cny"] for x in packages) != expected_total_ceiling_cny:
            return []
    if sum(len(x["product_names"]) for x in packages) > _MAX_TOTAL_ITEMS:
        return []
    return packages
