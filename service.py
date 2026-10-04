"""
Lotus Fin AI006 — Service Layer for Repayment / Stress Simulation.
Exposes Frappe whitelisted endpoints.
"""

import frappe
from frappe import _
import json
from decimal import Decimal

from .models import (
    LoanTerms,
    StressScenarioParams,
    AmortizationMethod,
    PaymentFrequency,
    StressType
)
from .engine import RepaymentEngine
from .stress import StressSimulationEngine
from .ai_advisor import RepaymentAdvisor


@frappe.whitelist()
def calculate_repayment_schedule(
    principal: float,
    annual_rate: float,
    term_months: int,
    amortization_method: str = "EQUAL_INSTALLMENT",
    payment_frequency: str = "MONTHLY",
    grace_period_months: int = 0,
    processing_fee_pct: float = 0.01,
    scenario_id: str = ""
):
    """
    API endpoint: Tính lịch trả nợ cơ bản.
    """
    try:
        terms = LoanTerms(
            principal=Decimal(str(principal)),
            annual_rate=Decimal(str(annual_rate)),
            term_months=term_months,
            amortization_method=AmortizationMethod(amortization_method),
            payment_frequency=PaymentFrequency(payment_frequency),
            grace_period_months=grace_period_months,
            processing_fee_pct=Decimal(str(processing_fee_pct)),
            scenario_id=scenario_id
        )

        engine = RepaymentEngine()
        result = engine.calculate_schedule(terms)

        advisor = RepaymentAdvisor()
        explanation = advisor.explain_schedule(result)

        return {
            "status": "success",
            "data": {
                "schedule_id": result.schedule_id,
                "summary": result.summary,
                "payment_schedule": result.payment_schedule,
                "cashflow_impact": result.cashflow_impact,
                "assumptions": result.assumptions,
                "limitations": result.limitations,
                "ai_explanation": explanation
            }
        }
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="AI006 Calculate Schedule Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def run_stress_test(
    principal: float,
    annual_rate: float,
    term_months: int,
    stress_type: str,
    rate_shock_bps: int = 0,
    term_extension_months: int = 0,
    early_repayment_month: int = 0,
    grace_period_months: int = 0,
    amortization_method: str = "EQUAL_INSTALLMENT",
    scenario_id: str = ""
):
    """
    API endpoint: Chạy stress test (kiểm tra sức chịu đựng).
    """
    try:
        base_terms = LoanTerms(
            principal=Decimal(str(principal)),
            annual_rate=Decimal(str(annual_rate)),
            term_months=term_months,
            amortization_method=AmortizationMethod(amortization_method),
            scenario_id=scenario_id
        )

        stress_params = StressScenarioParams(
            stress_type=StressType(stress_type),
            rate_shock_bps=rate_shock_bps,
            term_extension_months=term_extension_months,
            early_repayment_month=early_repayment_month,
            grace_period_months=grace_period_months
        )

        stress_engine = StressSimulationEngine()
        result = stress_engine.run_stress_test(base_terms, stress_params)

        advisor = RepaymentAdvisor()
        explanation = advisor.explain_stress_test(result)

        return {
            "status": "success",
            "data": {
                "stress_id": result.stress_id,
                "stress_type": result.stress_type,
                "stress_description": result.stress_description,
                "comparison_kpis": result.comparison_kpis,
                "recommendations": result.recommendations,
                "base_summary": result.base_schedule_summary,
                "stressed_summary": result.stressed_schedule_summary,
                "ai_explanation": explanation
            }
        }
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="AI006 Stress Test Error")
        return {"status": "error", "message": str(e)}
