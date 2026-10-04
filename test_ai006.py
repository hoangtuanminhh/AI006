"""
Unit tests for AI006 Repayment / Stress Simulation.
Verifies deterministic accuracy using Decimal.
"""

import unittest
from decimal import Decimal
import sys
import os

# Add parent dir to path to allow importing lotus_fin.AI006 if needed, 
# or just test relative to current package if possible.
try:
    from lotus_fin.AI006.models import LoanTerms, AmortizationMethod, StressScenarioParams, StressType
    from lotus_fin.AI006.engine import RepaymentEngine
    from lotus_fin.AI006.stress import StressSimulationEngine
except ImportError:
    # Try with inner package
    from lotus_fin.lotus_fin.AI006.models import LoanTerms, AmortizationMethod, StressScenarioParams, StressType
    from lotus_fin.lotus_fin.AI006.engine import RepaymentEngine
    from lotus_fin.lotus_fin.AI006.stress import StressSimulationEngine

class TestAI006RepaymentEngine(unittest.TestCase):
    def setUp(self):
        self.engine = RepaymentEngine()

    def test_pmt_equal_installment(self):
        """Test phương pháp trả góp đều (PMT)."""
        terms = LoanTerms(
            principal=Decimal("100000000"),
            annual_rate=Decimal("0.12"),  # 1% per month
            term_months=12,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT
        )
        result = self.engine.calculate_schedule(terms)
        
        self.assertEqual(len(result.payment_schedule), 12)
        # Expected PMT for 100M, 1%/mo, 12 mos = 8,884,878.86 ~ 8,884,879
        first_payment = result.payment_schedule[0]['total_payment']
        self.assertTrue(8884878 <= first_payment <= 8884880)
        
        # Balance must reach 0
        self.assertEqual(result.payment_schedule[-1]['closing_balance'], 0.0)

    def test_equal_principal(self):
        """Test phương pháp gốc đều, lãi giảm dần."""
        terms = LoanTerms(
            principal=Decimal("120000000"),
            annual_rate=Decimal("0.12"),
            term_months=12,
            amortization_method=AmortizationMethod.EQUAL_PRINCIPAL
        )
        result = self.engine.calculate_schedule(terms)
        
        # Principal payment should be exactly 10,000,000 each month
        first_prin = result.payment_schedule[0]['principal_payment']
        self.assertEqual(first_prin, 10000000.0)
        
        last_prin = result.payment_schedule[-1]['principal_payment']
        self.assertEqual(last_prin, 10000000.0)
        
        # First month interest = 1,200,000
        self.assertEqual(result.payment_schedule[0]['interest_payment'], 1200000.0)


class TestAI006StressEngine(unittest.TestCase):
    def setUp(self):
        self.stress_engine = StressSimulationEngine()

    def test_rate_shock(self):
        """Test tăng lãi suất 2% (200 bps)."""
        base_terms = LoanTerms(
            principal=Decimal("100000000"),
            annual_rate=Decimal("0.10"),
            term_months=12,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT
        )
        params = StressScenarioParams(
            stress_type=StressType.RATE_SHOCK,
            rate_shock_bps=200
        )
        
        result = self.stress_engine.run_stress_test(base_terms, params)
        
        # Stressed rate should be 12%
        kpis = result.comparison_kpis
        interest_kpi = next(k for k in kpis if k['kpi_name'] == "Total Interest")
        
        self.assertGreater(interest_kpi['absolute_change'], 0)
        self.assertEqual(interest_kpi['impact_assessment'], "ADVERSE")


if __name__ == "__main__":
    unittest.main()
