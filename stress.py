"""
Lotus Fin AI006 — Stress Simulation Engine.
Compares Base Schedule vs Stressed Schedule across multiple stress scenarios:
1. Rate Shock (Lãi suất tăng đột biến)
2. Term Extension (Kéo dài kỳ hạn)
3. Early Repayment (Trả nợ trước hạn)
4. Grace Period (Ân hạn gốc)
5. Combined (Kết hợp nhiều yếu tố)
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import copy

from .models import (
    LoanTerms,
    StressScenarioParams,
    StressComparisonKPI,
    StressTestResult,
    StressType
)
from .engine import RepaymentEngine, MONEY


class StressSimulationEngine:
    """
    Công cụ kiểm tra sức chịu đựng tài chính cho khoản vay.
    So sánh Kịch bản gốc (Base) vs Kịch bản stress để đánh giá rủi ro.
    """

    def __init__(self):
        self.repayment_engine = RepaymentEngine()

    def run_stress_test(
        self,
        base_terms: LoanTerms,
        stress_params: StressScenarioParams
    ) -> StressTestResult:
        """Điểm vào chính: Chạy stress test và trả về kết quả so sánh hoàn chỉnh."""

        # 1. Tính lịch trả nợ gốc (Baseline)
        base_result = self.repayment_engine.calculate_schedule(base_terms)

        # 2. Tạo bản sao điều kiện vay và áp dụng stress
        stressed_terms = self._apply_stress(base_terms, stress_params)
        stressed_result = self.repayment_engine.calculate_schedule(stressed_terms)

        # 3. Xử lý riêng cho Early Repayment (cắt lịch tại tháng trả trước hạn)
        early_repayment_detail = None
        if stress_params.stress_type == StressType.EARLY_REPAYMENT and stress_params.early_repayment_month > 0:
            early_repayment_detail = self._calculate_early_repayment(
                base_result, stress_params.early_repayment_month, stress_params.early_repayment_penalty_pct, base_terms
            )
            # Override stressed summary with early repayment data
            stressed_result = early_repayment_detail["result"]

        # 4. So sánh KPIs
        comparison = self._compare_summaries(base_result.summary, stressed_result.summary, stress_params)

        # 5. Khuyến nghị
        recommendations = self._generate_recommendations(comparison, stress_params)

        limitations = [
            "Kết quả stress test mang cờ data_mode = 'simulation', không phải cam kết tín dụng.",
            "Lãi suất thả nổi được giả lập bằng mức cố định; biến động thực tế có thể khác.",
            "Phí phạt trả trước hạn được tính theo tỷ lệ cố định trên dư nợ còn lại tại thời điểm trả."
        ]

        return StressTestResult(
            stress_id=f"stress_{stress_params.stress_type.value.lower()}",
            scenario_id=base_terms.scenario_id,
            data_mode="simulation",
            stress_type=stress_params.stress_type.value,
            stress_description=stress_params.description or self._auto_description(stress_params),
            base_schedule_summary=base_result.summary,
            stressed_schedule_summary=stressed_result.summary,
            comparison_kpis=[self._kpi_to_dict(k) for k in comparison],
            base_payment_schedule=base_result.payment_schedule,
            stressed_payment_schedule=stressed_result.payment_schedule,
            recommendations=recommendations,
            limitations=limitations
        )

    def _apply_stress(self, base: LoanTerms, params: StressScenarioParams) -> LoanTerms:
        """Tạo bản sao LoanTerms đã áp dụng điều kiện stress."""
        stressed = LoanTerms(
            principal=base.principal,
            annual_rate=base.annual_rate,
            term_months=base.term_months,
            currency=base.currency,
            rate_type=base.rate_type,
            payment_frequency=base.payment_frequency,
            amortization_method=base.amortization_method,
            processing_fee_pct=base.processing_fee_pct,
            insurance_fee_pct=base.insurance_fee_pct,
            fee_timing=base.fee_timing,
            grace_period_months=base.grace_period_months,
            rounding_rule=base.rounding_rule,
            start_date=base.start_date,
            scenario_id=base.scenario_id,
            data_mode="simulation"
        )

        if params.stress_type == StressType.RATE_SHOCK:
            shock = Decimal(str(params.rate_shock_bps)) / Decimal("10000")
            stressed.annual_rate = (base.annual_rate + shock).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        elif params.stress_type == StressType.TERM_EXTENSION:
            stressed.term_months = base.term_months + params.term_extension_months

        elif params.stress_type == StressType.GRACE_PERIOD:
            stressed.grace_period_months = params.grace_period_months

        elif params.stress_type == StressType.COMBINED:
            if params.rate_shock_bps > 0:
                shock = Decimal(str(params.rate_shock_bps)) / Decimal("10000")
                stressed.annual_rate = (base.annual_rate + shock).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if params.term_extension_months > 0:
                stressed.term_months = base.term_months + params.term_extension_months
            if params.grace_period_months > 0:
                stressed.grace_period_months = params.grace_period_months

        # EARLY_REPAYMENT: Sử dụng cùng terms gốc, xử lý riêng trong _calculate_early_repayment

        return stressed

    def _calculate_early_repayment(
        self, base_result, payoff_month: int, penalty_pct: Decimal, base_terms: LoanTerms
    ) -> Dict[str, Any]:
        """Tính toán kịch bản trả trước hạn: cắt lịch tại tháng payoff, cộng phí phạt."""
        schedule = base_result.payment_schedule
        kept_payments = [p for p in schedule if p["period"] <= payoff_month]

        if not kept_payments:
            return {"result": base_result}

        last_period = kept_payments[-1]
        remaining_balance = Decimal(str(last_period["closing_balance"]))

        # Phí phạt trả trước hạn = penalty_pct × dư nợ còn lại
        penalty_fee = (remaining_balance * penalty_pct).quantize(MONEY, rounding=ROUND_HALF_UP)

        # Kỳ tất toán: Trả hết gốc + phí phạt
        final_interest = Decimal("0")  # Lãi đã tính trong kỳ cuối
        total_final = (remaining_balance + penalty_fee).quantize(MONEY, rounding=ROUND_HALF_UP)
        cum_principal = Decimal(str(last_period["cumulative_principal"])) + remaining_balance
        cum_interest = Decimal(str(last_period["cumulative_interest"]))

        payoff_record = {
            "period": payoff_month + 1,
            "payment_date": f"Tất toán trước hạn tại kỳ {payoff_month + 1}",
            "opening_balance": float(remaining_balance),
            "principal_payment": float(remaining_balance),
            "interest_payment": 0.0,
            "penalty_fee": float(penalty_fee),
            "total_payment": float(total_final),
            "closing_balance": 0.0,
            "cumulative_principal": float(cum_principal),
            "cumulative_interest": float(cum_interest)
        }
        kept_payments.append(payoff_record)

        # Xây dựng summary cho kịch bản trả trước hạn
        total_interest = float(cum_interest)
        total_repayment = float(cum_principal + cum_interest + penalty_fee + Decimal(str(base_result.fees.get("total_fees", 0))))

        early_summary = {
            "principal": float(base_terms.principal),
            "total_interest": total_interest,
            "total_fees": base_result.fees.get("total_fees", 0) + float(penalty_fee),
            "total_repayment": total_repayment,
            "total_periods": payoff_month + 1,
            "early_repayment_month": payoff_month,
            "penalty_fee": float(penalty_fee),
            "interest_saved": float(Decimal(str(base_result.summary["total_interest"])) - Decimal(str(total_interest))),
            "average_monthly_payment": total_repayment / (payoff_month + 1) if payoff_month > 0 else 0,
            "currency": base_terms.currency,
            "first_payment": kept_payments[0]["total_payment"] if kept_payments else 0,
            "last_payment": kept_payments[-1]["total_payment"] if kept_payments else 0,
            "interest_to_principal_ratio": total_interest / float(base_terms.principal) if float(base_terms.principal) > 0 else 0
        }

        from .models import RepaymentScheduleResult
        early_result = RepaymentScheduleResult(
            schedule_id=f"sched_early_payoff_m{payoff_month}",
            scenario_id=base_terms.scenario_id,
            data_mode="simulation",
            loan_terms=base_result.loan_terms,
            payment_schedule=kept_payments,
            summary=early_summary,
            cashflow_impact=[],
            fees=base_result.fees,
            assumptions=[f"Tất toán trước hạn toàn bộ dư nợ gốc tại tháng thứ {payoff_month}.",
                         f"Phí phạt trả trước hạn: {float(penalty_pct * 100):.1f}% trên dư nợ còn lại."],
            limitations=["Phí phạt thực tế có thể khác tùy theo hợp đồng cụ thể với ngân hàng."]
        )

        return {"result": early_result}

    def _compare_summaries(
        self, base_summary: Dict, stressed_summary: Dict, params: StressScenarioParams
    ) -> List[StressComparisonKPI]:
        """So sánh các chỉ số tổng quan giữa Baseline và Stressed."""
        kpis = []

        comparisons = [
            ("Total Interest", "total_interest", "VND"),
            ("Total Repayment", "total_repayment", "VND"),
            ("Average Monthly Payment", "average_monthly_payment", "VND"),
            ("Total Periods", "total_periods", "kỳ"),
            ("Interest/Principal Ratio", "interest_to_principal_ratio", "x"),
        ]

        for name, key, unit in comparisons:
            base_val = base_summary.get(key, 0)
            stress_val = stressed_summary.get(key, 0)
            abs_change = stress_val - base_val
            rel_change = abs_change / base_val if base_val != 0 else None

            # Đánh giá tác động
            if name in ("Total Interest", "Total Repayment", "Average Monthly Payment", "Interest/Principal Ratio"):
                impact = "FAVORABLE" if abs_change < 0 else ("ADVERSE" if abs_change > 0 else "NEUTRAL")
            elif name == "Total Periods":
                impact = "NEUTRAL" if abs_change == 0 else ("ADVERSE" if abs_change > 0 else "FAVORABLE")
            else:
                impact = "NEUTRAL"

            kpis.append(StressComparisonKPI(
                kpi_name=name,
                baseline_value=base_val,
                stressed_value=stress_val,
                absolute_change=round(abs_change, 2),
                relative_change=round(rel_change, 4) if rel_change is not None else None,
                unit=unit,
                impact_assessment=impact
            ))

        # Thêm KPI đặc biệt cho Early Repayment
        if params.stress_type == StressType.EARLY_REPAYMENT:
            interest_saved = stressed_summary.get("interest_saved", 0)
            penalty = stressed_summary.get("penalty_fee", 0)
            net_saving = interest_saved - penalty
            kpis.append(StressComparisonKPI(
                kpi_name="Net Savings (Interest Saved - Penalty)",
                baseline_value=0,
                stressed_value=round(net_saving, 2),
                absolute_change=round(net_saving, 2),
                relative_change=None,
                unit="VND",
                impact_assessment="FAVORABLE" if net_saving > 0 else "ADVERSE"
            ))

        return kpis

    def _generate_recommendations(
        self, kpis: List[StressComparisonKPI], params: StressScenarioParams
    ) -> List[str]:
        """Sinh khuyến nghị dựa trên kết quả so sánh KPIs."""
        recs = []

        if params.stress_type == StressType.RATE_SHOCK:
            total_interest_kpi = next((k for k in kpis if k.kpi_name == "Total Interest"), None)
            if total_interest_kpi and total_interest_kpi.absolute_change > 0:
                recs.append(
                    f"Nếu lãi suất tăng {params.rate_shock_bps} bps (+{params.rate_shock_bps / 100:.1f}%), "
                    f"tổng lãi phải trả tăng thêm {total_interest_kpi.absolute_change:,.0f} VND. "
                    f"Cân nhắc khóa lãi suất cố định nếu có thể."
                )

        elif params.stress_type == StressType.TERM_EXTENSION:
            recs.append(
                f"Kéo dài kỳ hạn thêm {params.term_extension_months} tháng giúp giảm áp lực trả nợ hàng tháng "
                f"nhưng tăng tổng chi phí lãi vay. Phù hợp khi dòng tiền đang gặp khó khăn ngắn hạn."
            )

        elif params.stress_type == StressType.EARLY_REPAYMENT:
            net_kpi = next((k for k in kpis if "Net Savings" in k.kpi_name), None)
            if net_kpi and net_kpi.stressed_value > 0:
                recs.append(
                    f"Trả trước hạn tại tháng {params.early_repayment_month} giúp tiết kiệm ròng "
                    f"{net_kpi.stressed_value:,.0f} VND (sau khi trừ phí phạt). Nên thực hiện nếu đủ thanh khoản."
                )
            elif net_kpi:
                recs.append(
                    f"Trả trước hạn tại tháng {params.early_repayment_month} không có lợi vì phí phạt "
                    f"cao hơn tiền lãi tiết kiệm được. Cân nhắc kéo dài thêm vài tháng trước khi tất toán."
                )

        elif params.stress_type == StressType.GRACE_PERIOD:
            recs.append(
                f"Ân hạn gốc {params.grace_period_months} tháng giúp giảm áp lực dòng tiền giai đoạn đầu "
                f"nhưng tổng lãi vay sẽ tăng do dư nợ gốc duy trì lâu hơn."
            )

        if not recs:
            recs.append("Tham khảo báo cáo so sánh chi tiết giữa kịch bản gốc và kịch bản stress bên dưới.")

        return recs

    def _auto_description(self, params: StressScenarioParams) -> str:
        """Tự động sinh mô tả cho kịch bản stress."""
        if params.stress_type == StressType.RATE_SHOCK:
            return f"Lãi suất tăng {params.rate_shock_bps} basis points (+{params.rate_shock_bps / 100:.1f}%)"
        elif params.stress_type == StressType.TERM_EXTENSION:
            return f"Kéo dài kỳ hạn thêm {params.term_extension_months} tháng"
        elif params.stress_type == StressType.EARLY_REPAYMENT:
            return f"Trả trước hạn tại tháng thứ {params.early_repayment_month} (phí phạt {float(params.early_repayment_penalty_pct * 100):.1f}%)"
        elif params.stress_type == StressType.GRACE_PERIOD:
            return f"Ân hạn gốc {params.grace_period_months} tháng đầu"
        elif params.stress_type == StressType.COMBINED:
            parts = []
            if params.rate_shock_bps > 0:
                parts.append(f"+{params.rate_shock_bps}bps lãi suất")
            if params.term_extension_months > 0:
                parts.append(f"+{params.term_extension_months} tháng kỳ hạn")
            if params.grace_period_months > 0:
                parts.append(f"ân hạn {params.grace_period_months} tháng")
            return "Kết hợp: " + ", ".join(parts) if parts else "Kịch bản kết hợp"
        return "Kịch bản stress test"

    def _kpi_to_dict(self, kpi: StressComparisonKPI) -> Dict[str, Any]:
        return {
            "kpi_name": kpi.kpi_name,
            "baseline_value": kpi.baseline_value,
            "stressed_value": kpi.stressed_value,
            "absolute_change": kpi.absolute_change,
            "relative_change": kpi.relative_change,
            "unit": kpi.unit,
            "impact_assessment": kpi.impact_assessment
        }
