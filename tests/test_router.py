"""
Unit tests for the deterministic router service.
Uses pre-built RuleRouter objects without a DB.
"""
import pytest
from app.models.rule import RuleRouter
from app.services.router import route_entry_from_rules


def make_rule(name, pattern, target, entry_type, priority, is_active=True):
    r = RuleRouter()
    r.name = name
    r.pattern = pattern
    r.target = target
    r.entry_type = entry_type
    r.priority = priority
    r.is_active = is_active
    return r


DEFAULT_RULES = [
    make_rule("task_prefix",     r"^(TODO|TASK|tarea|hacer)", "tasks",         "task",        100),
    make_rule("income_keyword",  r"(ingreso|income|cobré|cobr)", "transactions", "transaction", 90),
    make_rule("expense_keyword", r"(gast|pagué|pague|compré|compre|expense|paid)", "transactions", "transaction", 80),
    make_rule("fact_keyword",    r"^(FACT|DATO|nota|note):",   "facts",         "fact",        70),
    make_rule("metric_keyword",  r"^(METRIC|METRICA|KPI):",    "metrics_daily", "metric",     60),
    make_rule("project_keyword", r"^(PROJECT|PROYECTO):",      "projects",      "project",    50),
    make_rule("default_note",    r".*",                        "facts",         "note",        0),
]


class TestRouterRules:
    def test_task_todo(self):
        result = route_entry_from_rules("TODO: fix the login bug", DEFAULT_RULES)
        assert result.target == "tasks"
        assert result.entry_type == "task"
        assert result.rule_name == "task_prefix"

    def test_task_tarea(self):
        result = route_entry_from_rules("tarea: llamar al cliente", DEFAULT_RULES)
        assert result.target == "tasks"

    def test_income(self):
        result = route_entry_from_rules("ingreso $1500 de freelance", DEFAULT_RULES)
        assert result.target == "transactions"
        assert result.entry_type == "transaction"
        assert result.rule_name == "income_keyword"

    def test_expense(self):
        result = route_entry_from_rules("gasté $30 en el supermercado", DEFAULT_RULES)
        assert result.target == "transactions"
        assert result.rule_name == "expense_keyword"

    def test_expense_paid(self):
        result = route_entry_from_rules("paid $99 for hosting", DEFAULT_RULES)
        assert result.target == "transactions"

    def test_fact(self):
        result = route_entry_from_rules("FACT: Python 3.12 lanzado", DEFAULT_RULES)
        assert result.target == "facts"
        assert result.entry_type == "fact"

    def test_metric(self):
        result = route_entry_from_rules("METRIC: steps=8500 count", DEFAULT_RULES)
        assert result.target == "metrics_daily"
        assert result.entry_type == "metric"

    def test_project(self):
        result = route_entry_from_rules("PROJECT: Nuevo sitio web", DEFAULT_RULES)
        assert result.target == "projects"
        assert result.entry_type == "project"

    def test_default_fallback(self):
        result = route_entry_from_rules("Hoy fue un buen día", DEFAULT_RULES)
        assert result.target == "facts"
        assert result.entry_type == "note"
        assert result.rule_name == "default_note"

    def test_priority_order(self):
        """task_prefix (100) beats income_keyword (90) for ambiguous text."""
        result = route_entry_from_rules("TODO cobré $100", DEFAULT_RULES)
        assert result.target == "tasks"

    def test_inactive_rule_skipped(self):
        rules = [
            make_rule("task_prefix", r"^TODO", "tasks", "task", 100, is_active=False),
            make_rule("default_note", r".*", "facts", "note", 0),
        ]
        result = route_entry_from_rules("TODO: something", rules)
        assert result.target == "facts"
        assert result.rule_name == "default_note"

    def test_bad_regex_skipped(self):
        rules = [
            make_rule("bad_rule", r"[invalid(", "tasks", "task", 100),
            make_rule("default_note", r".*", "facts", "note", 0),
        ]
        result = route_entry_from_rules("anything", rules)
        assert result.target == "facts"

    def test_no_rules_fallback(self):
        result = route_entry_from_rules("anything", [])
        assert result.entry_type == "note"
        assert result.target == "facts"
        assert result.rule_name is None
