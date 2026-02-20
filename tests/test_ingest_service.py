"""
Unit tests for the ingest service fan-out logic (no HTTP layer).
"""
import pytest
from decimal import Decimal
from datetime import date

from app.services.ingest import _extract_amount, _detect_tx_type


class TestExtractAmount:
    def test_plain_number(self):
        assert _extract_amount("gasté 150 en ropa") == Decimal("150")

    def test_dollar_sign(self):
        assert _extract_amount("paid $99.99") == Decimal("99.99")

    def test_euro_sign(self):
        assert _extract_amount("€ 250 groceries") == Decimal("250")

    def test_no_amount(self):
        assert _extract_amount("sin monto aquí") is None

    def test_commas(self):
        assert _extract_amount("$1,500 salary") == Decimal("1500")


class TestDetectTxType:
    def test_income_ingreso(self):
        assert _detect_tx_type("ingreso de $300") == "income"

    def test_income_cobr(self):
        assert _detect_tx_type("cobré $500 al cliente") == "income"

    def test_transfer(self):
        assert _detect_tx_type("transferí $200 a Juan") == "transfer"

    def test_expense_default(self):
        assert _detect_tx_type("gasté $50 en cena") == "expense"

    def test_expense_paid(self):
        assert _detect_tx_type("paid $30 for taxi") == "expense"
