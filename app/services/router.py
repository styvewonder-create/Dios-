"""
Deterministic router: matches a raw text entry against rules stored in
rules_router (ordered by priority DESC) and returns the matched rule
plus the derived entry_type.

Falls back to "note" / "facts" if no rule matches.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.rule import RuleRouter


@dataclass
class RoutingResult:
    entry_type: str
    target: str
    rule_name: Optional[str]


def route_entry(raw: str, db: Session) -> RoutingResult:
    """
    Evaluate active rules in priority order against `raw`.
    Returns the first matching rule's routing info.
    """
    rules: list[RuleRouter] = (
        db.query(RuleRouter)
        .filter(RuleRouter.is_active == True)  # noqa: E712
        .order_by(RuleRouter.priority.desc())
        .all()
    )

    for rule in rules:
        try:
            if re.search(rule.pattern, raw, re.IGNORECASE):
                return RoutingResult(
                    entry_type=rule.entry_type,
                    target=rule.target,
                    rule_name=rule.name,
                )
        except re.error:
            # Bad regex pattern — skip rule
            continue

    # Absolute fallback (should not happen if default_note rule exists)
    return RoutingResult(entry_type="note", target="facts", rule_name=None)


def route_entry_from_rules(raw: str, rules: list[RuleRouter]) -> RoutingResult:
    """Pure version that accepts pre-loaded rules (useful for testing)."""
    for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
        if not rule.is_active:
            continue
        try:
            if re.search(rule.pattern, raw, re.IGNORECASE):
                return RoutingResult(
                    entry_type=rule.entry_type,
                    target=rule.target,
                    rule_name=rule.name,
                )
        except re.error:
            continue
    return RoutingResult(entry_type="note", target="facts", rule_name=None)
