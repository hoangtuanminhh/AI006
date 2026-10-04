"""
Lotus Fin AI006 — Models & Type Definitions for Repayment / Stress Simulation.
Enforces:
1. Strict Decimal arithmetic throughout.
2. Immutability via dataclass patterns.
3. data_mode = 'simulation' invariant on all outputs.
4. Comprehensive Vietnamese+English docstrings.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


# ======================================================================
# ENUMS
# ======================================================================

class AmortizationMethod(str, Enum):
    """Phương pháp phân bổ nợ gốc và lãi."""
    EQUAL_INSTALLMENT = "EQUAL_INSTALLMENT"  # Trả góp đều (PMT): gốc + lãi cố định mỗi kỳ
    EQUAL_PRINCIPAL = "EQUAL_PRINCIPAL"      # Trả gốc đều, lãi giảm dần theo dư nợ
    FLAT_RATE = "FLAT_RATE"                  # Lãi phẳng: tính trên gốc ban đầu suốt kỳ vay
    BULLET = "BULLET"                        # Trả lãi hàng kỳ, trả toàn bộ gốc cuối kỳ


class PaymentFrequency(str, Enum):
    """Tần suất thanh toán."""
    MONTHLY = "MONTHLY"        # Hàng tháng
    QUARTERLY = "QUARTERLY"    # Hàng quý


class StressType(str, Enum):
    """Loại hình kiểm tra sức chịu đựng (Stress Test)."""
    RATE_SHOCK = "RATE_SHOCK"              # Lãi suất tăng đột biến
    TERM_EXTENSION = "TERM_EXTENSION"      # Kéo dài kỳ hạn vay
    EARLY_REPAYMENT = "EARLY_REPAYMENT"    # Trả nợ trước hạn
    GRACE_PERIOD = "GRACE_PERIOD"          # Ân hạn gốc đầu kỳ
    COMBINED = "COMBINED"                  # Kết hợp nhiều yếu tố


# ======================================================================
# LOAN INPUT
# ======================================================================

@dataclass
class LoanTerms:
    """Điều kiện khoản vay đầu vào cho Repayment Engine."""
    principal: Decimal                                                # Số tiền vay gốc (VND)
    annual_rate: Decimal                                              # Lãi suất danh nghĩa năm (0.10 = 10%)
    term_months: int                                                  # Thời hạn vay (tháng)
    currency: str = "VND"
    rate_type: str = "FIXED"                                          # FIXED | FLOATING
    payment_frequency: PaymentFrequency = PaymentFrequency.MONTHLY
    amortization_method: AmortizationMethod = AmortizationMethod.EQUAL_INSTALLMENT
    processing_fee_pct: Decimal = Decimal("0.01")                     # Phí xử lý hồ sơ (1%)
    insurance_fee_pct: Decimal = Decimal("0.0")                       # Phí bảo hiểm tín dụng
    fee_timing: str = "UPFRONT"                                       # UPFRONT | SPREAD
    grace_period_months: int = 0                                      # Số tháng ân hạn gốc
    rounding_rule: str = "ROUND_HALF_UP"
    start_date: str = "2026-10-01"                                    # Ngày giải ngân
    scenario_id: str = ""                                             # Liên kết AI-F005 nếu có
    data_mode: str = "simulation"                                     # Luôn luôn 'simulation'


# ======================================================================
# PAYMENT SCHEDULE
# ======================================================================

@dataclass
class PaymentRecord:
    """Bản ghi thanh toán cho một kỳ trong lịch trả nợ."""
    period: int                    # Kỳ thanh toán (1, 2, 3…)
    payment_date: str              # Ngày thanh toán (YYYY-MM-DD)
    opening_balance: float         # Dư nợ đầu kỳ
    principal_payment: float       # Phần trả gốc trong kỳ
    interest_payment: float        # Phần trả lãi trong kỳ
    total_payment: float           # Tổng thanh toán kỳ (Gốc + Lãi)
    closing_balance: float         # Dư nợ cuối kỳ
    cumulative_principal: float    # Tổng gốc đã trả lũy kế
    cumulative_interest: float     # Tổng lãi đã trả lũy kế


@dataclass
class RepaymentScheduleResult:
    """Kết quả hoàn chỉnh của lịch trả nợ."""
    schedule_id: str
    scenario_id: str
    data_mode: str = "simulation"
    loan_terms: Dict[str, Any] = field(default_factory=dict)
    payment_schedule: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    cashflow_impact: List[Dict[str, Any]] = field(default_factory=list)
    fees: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)


# ======================================================================
# STRESS TEST
# ======================================================================

@dataclass
class StressScenarioParams:
    """Tham số đầu vào cho kiểm tra sức chịu đựng (Stress Test)."""
    stress_type: StressType
    rate_shock_bps: int = 0                                           # Tăng lãi suất (basis points: 200 = +2%)
    term_extension_months: int = 0                                    # Kéo dài thêm X tháng
    early_repayment_month: int = 0                                    # Trả hết gốc tại tháng X
    early_repayment_penalty_pct: Decimal = Decimal("0.02")            # Phí phạt trả trước hạn (2%)
    grace_period_months: int = 0                                      # Ân hạn gốc X tháng đầu
    description: str = ""


@dataclass
class StressComparisonKPI:
    """So sánh một KPI giữa kịch bản gốc và kịch bản stress."""
    kpi_name: str
    baseline_value: float
    stressed_value: float
    absolute_change: float
    relative_change: Optional[float]
    unit: str
    impact_assessment: str  # "FAVORABLE" | "ADVERSE" | "NEUTRAL"


@dataclass
class StressTestResult:
    """Kết quả kiểm tra sức chịu đựng hoàn chỉnh."""
    stress_id: str
    scenario_id: str
    data_mode: str = "simulation"
    stress_type: str = ""
    stress_description: str = ""
    base_schedule_summary: Dict[str, Any] = field(default_factory=dict)
    stressed_schedule_summary: Dict[str, Any] = field(default_factory=dict)
    comparison_kpis: List[Dict[str, Any]] = field(default_factory=list)
    base_payment_schedule: List[Dict[str, Any]] = field(default_factory=list)
    stressed_payment_schedule: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
