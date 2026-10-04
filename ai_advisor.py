"""
Lotus Fin AI006 — AI Advisor for Repayment & Stress Simulation.
Generates grounded, narrative explanations from deterministic simulation results.
"""

from typing import Any, Dict, List
import json
from decimal import Decimal

from .models import RepaymentScheduleResult, StressTestResult


class RepaymentAdvisor:
    """
    AI Advisor giải thích kết quả giả lập lịch trả nợ và kiểm tra sức chịu đựng.
    Chỉ sử dụng dữ liệu tất định (deterministic) từ engine, không tự bịa số liệu.
    """

    def explain_schedule(self, result: RepaymentScheduleResult) -> Dict[str, Any]:
        """Tạo giải thích cho lịch trả nợ cơ bản."""
        summary = result.summary
        method_map = {
            "EQUAL_INSTALLMENT": "Trả góp đều (gốc + lãi cố định)",
            "EQUAL_PRINCIPAL": "Gốc đều, lãi giảm dần",
            "FLAT_RATE": "Lãi phẳng trên dư nợ gốc ban đầu",
            "BULLET": "Trả lãi hàng kỳ, trả toàn bộ gốc cuối kỳ"
        }
        method = method_map.get(result.loan_terms.get("amortization_method"), "Không xác định")

        narrative = (
            f"Với khoản vay {summary['principal']:,.0f} {summary.get('currency', 'VND')}, "
            f"áp dụng phương pháp {method} trong {summary['total_periods']} kỳ:\n"
            f"- Tổng tiền lãi dự kiến: {summary['total_interest']:,.0f} {summary.get('currency', 'VND')}\n"
            f"- Tổng chi phí (gồm phí): {summary['total_fees']:,.0f} {summary.get('currency', 'VND')}\n"
            f"- Thanh toán trung bình mỗi kỳ: {summary['average_monthly_payment']:,.0f} {summary.get('currency', 'VND')}\n\n"
        )
        
        narrative += "Lưu ý: " + " ".join(result.assumptions)

        return {
            "narrative": narrative,
            "data_mode": result.data_mode,
            "scenario_id": result.scenario_id
        }

    def explain_stress_test(self, result: StressTestResult) -> Dict[str, Any]:
        """Tạo giải thích cho kết quả kiểm tra sức chịu đựng."""
        narrative = f"Kết quả kiểm tra sức chịu đựng (Kịch bản: {result.stress_description}):\n\n"
        
        for kpi in result.comparison_kpis:
            if kpi['absolute_change'] == 0:
                continue
            
            direction = "Tăng" if kpi['absolute_change'] > 0 else "Giảm"
            icon = "🔴" if kpi['impact_assessment'] == "ADVERSE" else ("🟢" if kpi['impact_assessment'] == "FAVORABLE" else "⚪")
            
            narrative += f"{icon} **{kpi['kpi_name']}**: {direction} {abs(kpi['absolute_change']):,.0f} {kpi['unit']} "
            narrative += f"(Từ {kpi['baseline_value']:,.0f} lên {kpi['stressed_value']:,.0f})\n"

        narrative += "\n**Khuyến nghị từ AI:**\n"
        for rec in result.recommendations:
            narrative += f"- {rec}\n"

        return {
            "narrative": narrative,
            "data_mode": result.data_mode,
            "stress_id": result.stress_id,
            "scenario_id": result.scenario_id
        }
